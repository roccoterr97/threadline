/**
 * The on-time morning start: every decision the function's scheduled path
 * (`POST …/refresh-now/daily-start`) makes, with no Deno API and no network
 * access of its own.
 *
 * GitHub starts a scheduled workflow when it has room, often hours after the
 * time in its `cron` line. So a pg_cron job in the owner's database (migration
 * 0016) calls this path every 15 minutes, and once the owner's daily time has
 * passed in the owner's time zone it asks GitHub to start the workflow in
 * daily mode: at most once per owner-local day, never when that day's daily
 * run already started, and only when the runner is GitHub.
 *
 * `index.ts` supplies the outside world through `DailyStartPorts`, so this
 * file runs unchanged under Deno and under the dashboard's Vitest, where it is
 * tested. Nothing here returns or logs a secret or an upstream error body.
 */
import {
  buildWorkflowDispatch,
  codeForRunnerStatus,
  githubHeaders,
  RefreshCode,
  RefreshTarget,
  StoreError,
  WORKFLOW_DAILY_MODE,
  workflowApiUrl,
  type DispatchRequest,
  type GitHubConfig,
  type RefreshConfig,
} from './refresh.ts';

// ---------------------------------------------------------------------------
// Operational tuning
// ---------------------------------------------------------------------------

/** The function path pg_cron calls; migration 0016 and the set-up use the same. */
export const DAILY_START_PATH = '/daily-start';

/** The header pg_cron sends the shared key in (migration 0016's `request_daily_start`). */
export const DAILY_START_KEY_HEADER = 'X-Daily-Start-Key';

/** A shorter configured key is treated as missing, so a guessable one never works. */
export const MIN_DAILY_START_KEY_LENGTH = 32;

/** The title GitHub gives a daily run (the workflow's `run-name`). */
export const DAILY_RUN_TITLE = 'Threadline daily run';

/**
 * How far back runs are read. The owner's midnight is never more than a day
 * ago; the extra hour covers the 25-hour day when summer time ends.
 */
export const LOOKBACK_HOURS = 25;

/** GitHub runs read in one look: a day holds one daily run and a few dozen refreshes at most. */
export const GITHUB_RUNS_PAGE_SIZE = 100;

const MILLISECONDS_PER_HOUR = 3_600_000;
const MINUTES_PER_HOUR = 60;
const RUN_TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)(:[0-5]\d(\.\d+)?)?$/;
const GITHUB_RUN_COMPLETED = 'completed';
const GITHUB_RUN_SUCCEEDED = 'success';

// ---------------------------------------------------------------------------
// Vocabulary
// ---------------------------------------------------------------------------

/** Every answer the scheduled path gives. Only pg_cron's log ever reads them. */
export enum DailyStartCode {
  Started = 'started',
  MethodNotAllowed = 'method_not_allowed',
  NotAuthorised = 'not_authorised',
  NotSetUp = 'not_set_up',
  NotGitHub = 'not_github',
  TooEarly = 'too_early',
  AlreadyStarted = 'already_started',
  AlreadyRan = 'already_ran',
  RunnerFailed = 'runner_failed',
  DatabaseUnavailable = 'database_unavailable',
}

const HTTP_STATUS: Record<DailyStartCode, number> = {
  [DailyStartCode.Started]: 202,
  [DailyStartCode.MethodNotAllowed]: 405,
  [DailyStartCode.NotAuthorised]: 401,
  [DailyStartCode.NotSetUp]: 503,
  [DailyStartCode.NotGitHub]: 200,
  [DailyStartCode.TooEarly]: 200,
  [DailyStartCode.AlreadyStarted]: 200,
  [DailyStartCode.AlreadyRan]: 200,
  [DailyStartCode.RunnerFailed]: 502,
  [DailyStartCode.DatabaseUnavailable]: 503,
};

/** The owner's daily time and zone, as `app_settings` holds them. */
export interface OwnerSchedule {
  /** IANA zone, such as Europe/Paris. */
  timeZone: string;
  /** Postgres `time`, such as "07:00:00". */
  runAt: string;
}

/** The row that holds an owner-local day while its run is being started. */
export interface DayClaim {
  id: string;
}

/** A GET to GitHub's API. */
export interface ReadRequest {
  url: string;
  init: { method: 'GET'; headers: Record<string, string> };
}

/** One workflow run, as far as this file cares. */
export interface WorkflowRun {
  title: string;
  createdAt: Date;
  status: string;
  conclusion: string | null;
}

// ---------------------------------------------------------------------------
// The shared key
// ---------------------------------------------------------------------------

/**
 * Compares the key the caller sent with the configured one in time that does
 * not depend on where they differ, so the key cannot be guessed byte by byte.
 */
export function keysMatch(given: string | null, expected: string): boolean {
  const encoder = new TextEncoder();
  const sent = encoder.encode(given ?? '');
  const wanted = encoder.encode(expected);
  let difference = sent.length ^ wanted.length;
  for (let index = 0; index < wanted.length; index += 1) {
    difference |= (sent[index] ?? 0) ^ (wanted[index] ?? 0);
  }
  return difference === 0;
}

/** The configured key, or null when it is missing or too short to trust. */
export function usableKey(configured: string | undefined): string | null {
  const key = configured?.trim() ?? '';
  return key.length >= MIN_DAILY_START_KEY_LENGTH ? key : null;
}

// ---------------------------------------------------------------------------
// The owner's clock
// ---------------------------------------------------------------------------

/** A moment as the owner's wall clock shows it. */
export interface OwnerMoment {
  /** The owner's calendar date, as YYYY-MM-DD. */
  date: string;
  /** Minutes past the owner's midnight. */
  minutes: number;
}

/** What the owner's clock shows at `moment`, or null for a zone nobody knows. */
export function ownerMoment(moment: Date, timeZone: string): OwnerMoment | null {
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(moment);
  } catch (error) {
    if (error instanceof RangeError) return null;
    throw error;
  }
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((found) => found.type === type)?.value ?? '';
  return {
    date: `${part('year')}-${part('month')}-${part('day')}`,
    minutes: Number(part('hour')) * MINUTES_PER_HOUR + Number(part('minute')),
  };
}

/** Minutes past midnight of a Postgres `time` such as "07:00:00", or null when malformed. */
export function minutesPastMidnight(runAt: string): number | null {
  const found = RUN_TIME_PATTERN.exec(runAt.trim());
  if (found === null) return null;
  return Number(found[1]) * MINUTES_PER_HOUR + Number(found[2]);
}

export type DueVerdict =
  | { due: true; ownerDate: string }
  | { due: false; code: DailyStartCode.TooEarly | DailyStartCode.NotSetUp };

/** Whether the owner's daily time has passed today, in the owner's zone. */
export function dueToday(schedule: OwnerSchedule, now: Date): DueVerdict {
  const clock = ownerMoment(now, schedule.timeZone);
  const runAt = minutesPastMidnight(schedule.runAt);
  if (clock === null || runAt === null) return { due: false, code: DailyStartCode.NotSetUp };
  if (clock.minutes < runAt) return { due: false, code: DailyStartCode.TooEarly };
  return { due: true, ownerDate: clock.date };
}

/** Whether any of these moments falls on the owner's date, in the owner's zone. */
export function anyOnOwnerDate(moments: Date[], ownerDate: string, timeZone: string): boolean {
  return moments.some((moment) => ownerMoment(moment, timeZone)?.date === ownerDate);
}

/** The earliest moment whose runs can still belong to the owner's today. */
export function lookbackStart(now: Date): Date {
  return new Date(now.getTime() - LOOKBACK_HOURS * MILLISECONDS_PER_HOUR);
}

// ---------------------------------------------------------------------------
// What GitHub says has run
// ---------------------------------------------------------------------------

/** The GET that lists the workflow's runs created since a moment. */
export function buildRunsQuery(config: GitHubConfig, since: Date): ReadRequest {
  const query = new URLSearchParams({
    created: `>=${since.toISOString()}`,
    per_page: String(GITHUB_RUNS_PAGE_SIZE),
  });
  return {
    url: `${workflowApiUrl(config)}/runs?${query.toString()}`,
    init: { method: 'GET', headers: githubHeaders(config.token) },
  };
}

function readRun(item: unknown): WorkflowRun | null {
  if (typeof item !== 'object' || item === null) return null;
  const run = item as Record<string, unknown>;
  const { display_title: title, created_at: createdAt, status, conclusion } = run;
  if (typeof title !== 'string' || typeof createdAt !== 'string' || typeof status !== 'string') {
    return null;
  }
  const created = new Date(createdAt);
  if (Number.isNaN(created.getTime())) return null;
  return { title, createdAt: created, status, conclusion: typeof conclusion === 'string' ? conclusion : null };
}

/** The runs in GitHub's answer, or null when it is not the expected shape. */
export function readWorkflowRuns(body: unknown): WorkflowRun[] | null {
  if (typeof body !== 'object' || body === null) return null;
  const runs = (body as Record<string, unknown>).workflow_runs;
  if (!Array.isArray(runs)) return null;
  const read = runs.map(readRun);
  return read.every((run): run is WorkflowRun => run !== null) ? read : null;
}

/**
 * A daily run that is waiting, going, or finished well. One that failed or was
 * cancelled does not count, so the morning gets one more try.
 */
export function countsAsStarted(run: WorkflowRun): boolean {
  if (run.title !== DAILY_RUN_TITLE) return false;
  return run.status !== GITHUB_RUN_COMPLETED || run.conclusion === GITHUB_RUN_SUCCEEDED;
}

// ---------------------------------------------------------------------------
// The handler
// ---------------------------------------------------------------------------

type LogFields = Record<string, string | number | boolean | null>;

/** Everything the scheduled path needs from outside, built per request by `index.ts`. */
export interface DailyStartPorts {
  config: RefreshConfig | null;
  /** The DAILY_START_KEY function secret. */
  configuredKey: string | undefined;
  now: () => Date;
  /** The owner's zone and daily time; null when the row is missing. @throws {StoreError} */
  readSchedule: () => Promise<OwnerSchedule | null>;
  /** When daily runs that did not fail started, since a moment. @throws {StoreError} */
  readDailyRuns: (since: Date) => Promise<Date[]>;
  /** Claims an owner-local day; null when it is already claimed. @throws {StoreError} */
  claimDay: (ownerDate: string) => Promise<DayClaim | null>;
  /** Gives a day back after GitHub refused. @throws {StoreError} */
  releaseDay: (claim: DayClaim) => Promise<void>;
  /** Sends a request and returns the HTTP status. Throws when unreachable. */
  send: (request: DispatchRequest) => Promise<number>;
  /** Sends a GET and returns the status and the parsed body (null when not JSON). */
  fetchJson: (request: ReadRequest) => Promise<{ status: number; body: unknown }>;
  log: (event: string, fields: LogFields) => void;
}

interface Outcome {
  code: DailyStartCode;
  ownerDate?: string;
  runner?: RefreshCode;
}

function reply(outcome: Outcome): Response {
  const body = { code: outcome.code, owner_date: outcome.ownerDate, runner: outcome.runner };
  return new Response(JSON.stringify(body), {
    status: HTTP_STATUS[outcome.code],
    headers: { 'Content-Type': 'application/json' },
  });
}

function storeOutcome(error: StoreError): Outcome {
  return {
    code: error.code === RefreshCode.NotSetUp ? DailyStartCode.NotSetUp : DailyStartCode.DatabaseUnavailable,
  };
}

async function release(claim: DayClaim, ports: DailyStartPorts): Promise<void> {
  try {
    await ports.releaseDay(claim);
  } catch (error) {
    if (!(error instanceof StoreError)) throw error;
    // The day stays claimed, so GitHub's own late start is the morning's run.
    ports.log('daily_start.release_failed', { code: error.code });
  }
}

/** Asks GitHub whether today's daily run already started there; a code when it cannot say. */
async function startedOnGitHub(
  config: GitHubConfig,
  ownerDate: string,
  timeZone: string,
  ports: DailyStartPorts,
): Promise<boolean | RefreshCode> {
  let answer: { status: number; body: unknown };
  try {
    answer = await ports.fetchJson(buildRunsQuery(config, lookbackStart(ports.now())));
  } catch (error) {
    ports.log('daily_start.runner_unreachable', { kind: error instanceof Error ? error.name : 'unknown' });
    return RefreshCode.RunnerUnavailable;
  }
  const refused = codeForRunnerStatus(answer.status);
  if (refused !== null) return refused;
  const runs = readWorkflowRuns(answer.body);
  if (runs === null) return RefreshCode.RunnerUnavailable;
  const started = runs.filter(countsAsStarted).map((run) => run.createdAt);
  return anyOnOwnerDate(started, ownerDate, timeZone);
}

async function dispatchDaily(config: GitHubConfig, ports: DailyStartPorts): Promise<RefreshCode | null> {
  try {
    return codeForRunnerStatus(await ports.send(buildWorkflowDispatch(config, WORKFLOW_DAILY_MODE)));
  } catch (error) {
    // Only the kind of failure is logged: the message could echo the URL.
    ports.log('daily_start.runner_unreachable', { kind: error instanceof Error ? error.name : 'unknown' });
    return RefreshCode.RunnerUnavailable;
  }
}

/**
 * With the day claimed: looks at GitHub once more, then starts the run. The
 * claim is given back whenever nothing was started, so the next call retries.
 */
async function startClaimedDay(
  config: GitHubConfig,
  claim: DayClaim,
  ownerDate: string,
  timeZone: string,
  ports: DailyStartPorts,
): Promise<Outcome> {
  const onGitHub = await startedOnGitHub(config, ownerDate, timeZone, ports);
  if (onGitHub === true) return { code: DailyStartCode.AlreadyRan, ownerDate };
  const refusal = onGitHub === false ? await dispatchDaily(config, ports) : onGitHub;
  if (refusal === null) return { code: DailyStartCode.Started, ownerDate };
  await release(claim, ports);
  return { code: DailyStartCode.RunnerFailed, ownerDate, runner: refusal };
}

/** Decides and, when due, claims the owner's day and starts its run. */
async function startIfDue(config: GitHubConfig, ports: DailyStartPorts): Promise<Outcome> {
  const schedule = await ports.readSchedule();
  if (schedule === null) return { code: DailyStartCode.NotSetUp };
  const now = ports.now();
  const verdict = dueToday(schedule, now);
  if (!verdict.due) return { code: verdict.code };
  const { ownerDate } = verdict;
  const recorded = await ports.readDailyRuns(lookbackStart(now));
  if (anyOnOwnerDate(recorded, ownerDate, schedule.timeZone)) {
    return { code: DailyStartCode.AlreadyRan, ownerDate };
  }
  const claim = await ports.claimDay(ownerDate);
  if (claim === null) return { code: DailyStartCode.AlreadyStarted, ownerDate };
  return startClaimedDay(config, claim, ownerDate, schedule.timeZone, ports);
}

/** Checks the caller and the settings; an outcome means "stop here". */
function refuse(request: Request, ports: DailyStartPorts): Outcome | GitHubConfig {
  if (request.method !== 'POST') return { code: DailyStartCode.MethodNotAllowed };
  const key = usableKey(ports.configuredKey);
  if (key === null) return { code: DailyStartCode.NotSetUp };
  if (!keysMatch(request.headers.get(DAILY_START_KEY_HEADER), key)) {
    return { code: DailyStartCode.NotAuthorised };
  }
  const config = ports.config;
  if (config === null) return { code: DailyStartCode.NotSetUp };
  // Owners on the Claude cloud routine have their own schedule.
  if (config.target !== RefreshTarget.GitHub) return { code: DailyStartCode.NotGitHub };
  return config;
}

/** Answers one call from the pg_cron job. */
export async function handleDailyStart(request: Request, ports: DailyStartPorts): Promise<Response> {
  const checked = refuse(request, ports);
  if ('code' in checked) return reply(checked);
  let outcome: Outcome;
  try {
    outcome = await startIfDue(checked, ports);
  } catch (error) {
    if (!(error instanceof StoreError)) throw error;
    outcome = storeOutcome(error);
  }
  if (outcome.code === DailyStartCode.Started || outcome.code === DailyStartCode.RunnerFailed) {
    ports.log(`daily_start.${outcome.code}`, {
      owner_date: outcome.ownerDate ?? null,
      runner: outcome.runner ?? null,
    });
  }
  return reply(outcome);
}
