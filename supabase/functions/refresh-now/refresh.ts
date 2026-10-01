/**
 * "Refresh now": every decision the Edge Function makes, with no Deno API and
 * no network access of its own.
 *
 * `index.ts` supplies the outside world through `RefreshPorts` (the database,
 * the clock, the outgoing HTTP call), so this file runs unchanged under Deno
 * and under the dashboard's Vitest, where it is tested.
 *
 * Nothing here returns or logs a secret or an upstream error body: every
 * failure is reduced to one of the stable `RefreshCode` values.
 */

// ---------------------------------------------------------------------------
// Operational tuning
// ---------------------------------------------------------------------------

/** A run marked "running" that started longer ago than this is treated as dead. */
export const RUN_IN_PROGRESS_WINDOW_MINUTES = 30;

/**
 * The shortest gap between two refreshes started from the dashboard. The
 * database enforces the same length (migration 0014's `cooldown_until`
 * default); a backend test keeps the two equal.
 */
export const REFRESH_COOLDOWN_MINUTES = 10;

/** The workflow file the GitHub target starts (agreed with the workflow's author). */
export const GITHUB_WORKFLOW_FILE = 'threadline-run.yml';

/** The branch the GitHub workflow runs on when GITHUB_REF is not set. */
export const DEFAULT_GITHUB_REF = 'main';

/** The one version value the routine fire endpoint accepts. */
export const ANTHROPIC_API_VERSION = '2023-06-01';

/** The GitHub REST API version this request was written against. */
export const GITHUB_API_VERSION = '2022-11-28';

/** What the routine's saved prompt reads to know this is a quick refresh. */
export const ROUTINE_REFRESH_TEXT = 'mode: refresh';

/** The workflow input value that selects a quick refresh. */
export const WORKFLOW_REFRESH_MODE = 'refresh';

const MILLISECONDS_PER_MINUTE = 60_000;
const MILLISECONDS_PER_SECOND = 1_000;
const GITHUB_API_ORIGIN = 'https://api.github.com';
const USER_AGENT = 'threadline-refresh-now';

// Strict shapes, so a mistyped secret can never send the token somewhere else.
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const REF_PATTERN = /^[A-Za-z0-9._/-]+$/;
const ROUTINE_FIRE_URL_PATTERN =
  /^https:\/\/api\.anthropic\.com\/v1\/claude_code\/routines\/trig_[A-Za-z0-9_-]+\/fire$/;
const LOCAL_ORIGIN_PATTERN = /^http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?$/;

// ---------------------------------------------------------------------------
// Vocabulary
// ---------------------------------------------------------------------------

/** Every answer the function gives. The dashboard turns each into plain English. */
export enum RefreshCode {
  Started = 'started',
  MethodNotAllowed = 'method_not_allowed',
  OriginNotAllowed = 'origin_not_allowed',
  NotSignedIn = 'not_signed_in',
  NotOwner = 'not_owner',
  NotSetUp = 'not_set_up',
  AlreadyRunning = 'already_running',
  TooSoon = 'too_soon',
  RunnerAuthFailed = 'runner_auth_failed',
  RunnerNotFound = 'runner_not_found',
  RunnerRejected = 'runner_rejected',
  RunnerRateLimited = 'runner_rate_limited',
  RunnerUnavailable = 'runner_unavailable',
  DatabaseUnavailable = 'database_unavailable',
}

/** Where the extra run is started. */
export enum RefreshTarget {
  GitHub = 'github',
  ClaudeRoutine = 'claude_routine',
}

/** The answer to "is the caller the owner of this dashboard?". */
export enum OwnerCheck {
  Owner = 'owner',
  NotOwner = 'not_owner',
  NotSignedIn = 'not_signed_in',
  Unavailable = 'unavailable',
}

const HTTP_STATUS: Record<RefreshCode, number> = {
  [RefreshCode.Started]: 202,
  [RefreshCode.MethodNotAllowed]: 405,
  [RefreshCode.OriginNotAllowed]: 403,
  [RefreshCode.NotSignedIn]: 401,
  [RefreshCode.NotOwner]: 403,
  [RefreshCode.NotSetUp]: 503,
  [RefreshCode.AlreadyRunning]: 409,
  [RefreshCode.TooSoon]: 429,
  [RefreshCode.RunnerAuthFailed]: 502,
  [RefreshCode.RunnerNotFound]: 502,
  [RefreshCode.RunnerRejected]: 502,
  [RefreshCode.RunnerRateLimited]: 502,
  [RefreshCode.RunnerUnavailable]: 502,
  [RefreshCode.DatabaseUnavailable]: 503,
};

/** A database failure the handler knows how to explain. */
export class StoreError extends Error {
  readonly code: RefreshCode;

  constructor(code: RefreshCode) {
    super(`refresh store failed: ${code}`);
    this.name = 'StoreError';
    this.code = code;
  }
}

// PostgREST / Postgres codes: a missing table or function means migration 0013
// (or 0002) has not been applied; PGRST301 is an expired or invalid sign-in.
const NOT_SET_UP_DATABASE_CODES = new Set(['42P01', '42883', 'PGRST202', 'PGRST205']);
const NOT_SIGNED_IN_DATABASE_CODES = new Set(['PGRST301', 'PGRST302']);

/** Postgres "exclusion_violation": another request already holds the cool-down. */
export const COOLDOWN_TAKEN_DATABASE_CODE = '23P01';

/** Turns a database error code into the answer the dashboard understands. */
export function codeForDatabaseError(code: string | undefined): RefreshCode {
  if (code !== undefined && NOT_SET_UP_DATABASE_CODES.has(code)) return RefreshCode.NotSetUp;
  if (code !== undefined && NOT_SIGNED_IN_DATABASE_CODES.has(code)) return RefreshCode.NotSignedIn;
  return RefreshCode.DatabaseUnavailable;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export type RefreshConfig =
  | { target: RefreshTarget.GitHub; token: string; repository: string; ref: string }
  | { target: RefreshTarget.ClaudeRoutine; token: string; fireUrl: string };

/** Reads one function secret; `Deno.env.get` in production. */
export type ReadSetting = (name: string) => string | undefined;

function setting(read: ReadSetting, name: string): string | null {
  const value = read(name)?.trim() ?? '';
  return value === '' ? null : value;
}

function readGitHubConfig(read: ReadSetting): RefreshConfig | null {
  const token = setting(read, 'GITHUB_TOKEN_REFRESH');
  const repository = setting(read, 'GITHUB_REPOSITORY');
  const ref = setting(read, 'GITHUB_REF') ?? DEFAULT_GITHUB_REF;
  if (token === null || repository === null) return null;
  if (!REPOSITORY_PATTERN.test(repository) || !REF_PATTERN.test(ref)) return null;
  return { target: RefreshTarget.GitHub, token, repository, ref };
}

function readRoutineConfig(read: ReadSetting): RefreshConfig | null {
  const token = setting(read, 'ROUTINE_TOKEN');
  const fireUrl = setting(read, 'ROUTINE_FIRE_URL');
  if (token === null || fireUrl === null || !ROUTINE_FIRE_URL_PATTERN.test(fireUrl)) return null;
  return { target: RefreshTarget.ClaudeRoutine, token, fireUrl };
}

/**
 * The runner settings, or null when they are missing or malformed.
 * REFRESH_TARGET defaults to GitHub, the main runner.
 */
export function readConfig(read: ReadSetting): RefreshConfig | null {
  const target = setting(read, 'REFRESH_TARGET') ?? RefreshTarget.GitHub;
  if (target === RefreshTarget.GitHub) return readGitHubConfig(read);
  if (target === RefreshTarget.ClaudeRoutine) return readRoutineConfig(read);
  return null;
}

// ---------------------------------------------------------------------------
// Cross-origin access
// ---------------------------------------------------------------------------

function normaliseOrigin(value: string | undefined): string | null {
  const trimmed = value?.trim().replace(/\/+$/, '') ?? '';
  return trimmed === '' ? null : trimmed;
}

/** The dashboard's own address, or a local development server. */
export function isAllowedOrigin(origin: string, dashboardOrigin: string | undefined): boolean {
  return origin === normaliseOrigin(dashboardOrigin) || LOCAL_ORIGIN_PATTERN.test(origin);
}

/** CORS headers for an allowed origin; none at all for anyone else. */
export function corsHeaders(
  origin: string | null,
  dashboardOrigin: string | undefined,
): Record<string, string> {
  if (origin === null || !isAllowedOrigin(origin, dashboardOrigin)) return { Vary: 'Origin' };
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info',
    'Access-Control-Max-Age': '600',
    Vary: 'Origin',
  };
}

// ---------------------------------------------------------------------------
// Guards
// ---------------------------------------------------------------------------

/** What the database says about recent runs and refreshes. */
export interface Activity {
  /** When the newest run still marked "running" started, if any. */
  runningSince: Date | null;
  /** When the dashboard last started a refresh, if ever. */
  lastRequestAt: Date | null;
}

export type GuardVerdict =
  | { code: RefreshCode.Started }
  | { code: RefreshCode.AlreadyRunning }
  | { code: RefreshCode.TooSoon; retryAfterSeconds: number };

function minutesToMs(minutes: number): number {
  return minutes * MILLISECONDS_PER_MINUTE;
}

/** Refuses a refresh while a run is going or right after the previous one. */
export function checkGuards(activity: Activity, now: Date): GuardVerdict {
  const nowMs = now.getTime();
  const { runningSince, lastRequestAt } = activity;
  if (
    runningSince !== null &&
    nowMs - runningSince.getTime() < minutesToMs(RUN_IN_PROGRESS_WINDOW_MINUTES)
  ) {
    return { code: RefreshCode.AlreadyRunning };
  }
  if (lastRequestAt === null) return { code: RefreshCode.Started };
  const waitMs = lastRequestAt.getTime() + minutesToMs(REFRESH_COOLDOWN_MINUTES) - nowMs;
  if (waitMs <= 0) return { code: RefreshCode.Started };
  return { code: RefreshCode.TooSoon, retryAfterSeconds: Math.ceil(waitMs / MILLISECONDS_PER_SECOND) };
}

/** The earliest `started_at` that can still count as "running". */
export function runningWindowStart(now: Date): Date {
  return new Date(now.getTime() - minutesToMs(RUN_IN_PROGRESS_WINDOW_MINUTES));
}

// ---------------------------------------------------------------------------
// The outgoing request
// ---------------------------------------------------------------------------

export interface DispatchRequest {
  url: string;
  init: { method: 'POST'; headers: Record<string, string>; body: string };
}

/** The HTTP call that starts one quick run on the configured runner. */
export function buildDispatch(config: RefreshConfig): DispatchRequest {
  if (config.target === RefreshTarget.GitHub) {
    return {
      url: `${GITHUB_API_ORIGIN}/repos/${config.repository}/actions/workflows/${GITHUB_WORKFLOW_FILE}/dispatches`,
      init: {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: `Bearer ${config.token}`,
          'Content-Type': 'application/json',
          'User-Agent': USER_AGENT,
          'X-GitHub-Api-Version': GITHUB_API_VERSION,
        },
        body: JSON.stringify({ ref: config.ref, inputs: { mode: WORKFLOW_REFRESH_MODE } }),
      },
    };
  }
  return {
    url: config.fireUrl,
    init: {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${config.token}`,
        'anthropic-version': ANTHROPIC_API_VERSION,
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
      },
      body: JSON.stringify({ text: ROUTINE_REFRESH_TEXT }),
    },
  };
}

/** Maps the runner's HTTP status to an answer; null means it accepted. */
export function codeForRunnerStatus(status: number): RefreshCode | null {
  if (status >= 200 && status < 300) return null;
  if (status === 401 || status === 403) return RefreshCode.RunnerAuthFailed;
  if (status === 404) return RefreshCode.RunnerNotFound;
  if (status === 400 || status === 409 || status === 422) return RefreshCode.RunnerRejected;
  if (status === 429) return RefreshCode.RunnerRateLimited;
  return RefreshCode.RunnerUnavailable;
}

// ---------------------------------------------------------------------------
// The handler
// ---------------------------------------------------------------------------

type LogFields = Record<string, string | number | boolean | null>;

/** The stored request that holds the cool-down while the run is being started. */
export interface Claim {
  id: string;
}

/** Everything the handler needs from outside, built per request by `index.ts`. */
export interface RefreshPorts {
  config: RefreshConfig | null;
  dashboardOrigin: string | undefined;
  now: () => Date;
  checkOwner: () => Promise<OwnerCheck>;
  /** @throws {StoreError} */
  readActivity: () => Promise<Activity>;
  /**
   * Stores the request, which the database accepts only once per cool-down.
   * Resolves to null when another request already holds it.
   * @throws {StoreError}
   */
  claimRequest: (target: RefreshTarget) => Promise<Claim | null>;
  /** Gives the cool-down back after the runner refused. @throws {StoreError} */
  releaseRequest: (claim: Claim) => Promise<void>;
  /** Sends the request and returns the HTTP status. Throws when unreachable. */
  send: (request: DispatchRequest) => Promise<number>;
  log: (event: string, fields: LogFields) => void;
}

interface ReplyExtras {
  target?: RefreshTarget;
  requestedAt?: Date;
  retryAfterSeconds?: number;
}

function reply(
  code: RefreshCode,
  cors: Record<string, string>,
  extras: ReplyExtras = {},
): Response {
  const headers: Record<string, string> = { ...cors, 'Content-Type': 'application/json' };
  if (extras.retryAfterSeconds !== undefined) {
    headers['Retry-After'] = String(extras.retryAfterSeconds);
  }
  const body = {
    code,
    target: extras.target,
    requested_at: extras.requestedAt?.toISOString(),
    retry_after_seconds: extras.retryAfterSeconds,
  };
  return new Response(JSON.stringify(body), { status: HTTP_STATUS[code], headers });
}

const OWNER_REFUSALS: Record<Exclude<OwnerCheck, OwnerCheck.Owner>, RefreshCode> = {
  [OwnerCheck.NotOwner]: RefreshCode.NotOwner,
  [OwnerCheck.NotSignedIn]: RefreshCode.NotSignedIn,
  [OwnerCheck.Unavailable]: RefreshCode.DatabaseUnavailable,
};

/** Checks the caller before anything else; null means "carry on". */
async function refuseCaller(request: Request, ports: RefreshPorts): Promise<RefreshCode | null> {
  if (request.method !== 'POST') return RefreshCode.MethodNotAllowed;
  if (!request.headers.get('Authorization')) return RefreshCode.NotSignedIn;
  const owner = await ports.checkOwner();
  return owner === OwnerCheck.Owner ? null : OWNER_REFUSALS[owner];
}

async function readVerdict(ports: RefreshPorts): Promise<GuardVerdict | RefreshCode> {
  try {
    return checkGuards(await ports.readActivity(), ports.now());
  } catch (error) {
    if (error instanceof StoreError) return error.code;
    throw error;
  }
}

async function dispatch(config: RefreshConfig, ports: RefreshPorts): Promise<RefreshCode | null> {
  try {
    return codeForRunnerStatus(await ports.send(buildDispatch(config)));
  } catch (error) {
    // Only the kind of failure is logged: the message could echo the URL.
    ports.log('refresh.runner_unreachable', {
      target: config.target,
      kind: error instanceof Error ? error.name : 'unknown',
    });
    return RefreshCode.RunnerUnavailable;
  }
}

/** The whole cool-down, for a press that lost the race to another one. */
const COOLDOWN_SECONDS =
  (REFRESH_COOLDOWN_MINUTES * MILLISECONDS_PER_MINUTE) / MILLISECONDS_PER_SECOND;

/**
 * Takes the cool-down before the runner is asked, so two presses a moment
 * apart can never both start a run: the database lets only one row in.
 */
async function claim(
  target: RefreshTarget,
  ports: RefreshPorts,
): Promise<Claim | GuardVerdict | RefreshCode> {
  try {
    const claimed = await ports.claimRequest(target);
    return claimed ?? { code: RefreshCode.TooSoon, retryAfterSeconds: COOLDOWN_SECONDS };
  } catch (error) {
    if (error instanceof StoreError) return error.code;
    throw error;
  }
}

async function release(claimed: Claim, target: RefreshTarget, ports: RefreshPorts): Promise<void> {
  try {
    await ports.releaseRequest(claimed);
  } catch (error) {
    if (!(error instanceof StoreError)) throw error;
    // Nothing started; the next press only has to wait out the cool-down.
    ports.log('refresh.release_failed', { target, code: error.code });
  }
}

function replyToVerdict(
  verdict: GuardVerdict | RefreshCode,
  cors: Record<string, string>,
  target: RefreshTarget,
): Response {
  if (typeof verdict === 'string') return reply(verdict, cors, { target });
  if (verdict.code === RefreshCode.TooSoon) {
    return reply(verdict.code, cors, { target, retryAfterSeconds: verdict.retryAfterSeconds });
  }
  return reply(verdict.code, cors, { target });
}

/** Answers one request to start a refresh. */
export async function handleRefresh(request: Request, ports: RefreshPorts): Promise<Response> {
  const origin = request.headers.get('Origin');
  const cors = corsHeaders(origin, ports.dashboardOrigin);
  if (origin !== null && !isAllowedOrigin(origin, ports.dashboardOrigin)) {
    return reply(RefreshCode.OriginNotAllowed, cors);
  }
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });

  const callerRefusal = await refuseCaller(request, ports);
  if (callerRefusal !== null) return reply(callerRefusal, cors);

  const config = ports.config;
  if (config === null) return reply(RefreshCode.NotSetUp, cors);
  const { target } = config;

  // The read gives the usual answers (a run is going, wait N seconds); the
  // claim is what makes two simultaneous presses start one run, not two.
  const verdict = await readVerdict(ports);
  if (typeof verdict === 'string' || verdict.code !== RefreshCode.Started) {
    return replyToVerdict(verdict, cors, target);
  }
  const claimed = await claim(target, ports);
  if (typeof claimed === 'string' || 'code' in claimed) return replyToVerdict(claimed, cors, target);

  const requestedAt = ports.now();
  const refusal = await dispatch(config, ports);
  if (refusal !== null) {
    await release(claimed, target, ports);
    ports.log('refresh.refused_by_runner', { target, code: refusal });
    return reply(refusal, cors, { target });
  }

  ports.log('refresh.started', { target });
  return reply(RefreshCode.Started, cors, { target, requestedAt });
}
