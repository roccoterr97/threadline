/**
 * Supabase Edge Function "refresh-now": the dashboard's "Refresh now" button,
 * and the on-time morning start.
 *
 * The button: it checks that the caller is the dashboard's owner, refuses
 * while a run is going or right after the previous refresh, claims the
 * cool-down in the database, then asks the configured runner (a GitHub
 * Actions workflow, or a Claude cloud routine) for one quick extra run.
 *
 * The on-time morning start (path `…/refresh-now/daily-start`): a pg_cron job
 * in the database calls it every 15 minutes with a shared key, and it starts
 * the day's daily run on GitHub once the owner's daily time has passed. It
 * lives in this function, beside the button, so the two share the runner's
 * settings and one deploy; the path keeps the two callers apart.
 *
 * The runner's key lives only in this function's secrets. This file only
 * connects `refresh.ts` and `daily.ts` to Deno and the database; every
 * decision is made (and tested) there. Setup: docs/refresh-now.md.
 */
import { createClient, type SupabaseClient } from 'npm:@supabase/supabase-js@2';
import {
  DAILY_START_PATH,
  handleDailyStart,
  type DailyStartPorts,
  type DayClaim,
  type OwnerSchedule,
  type ReadRequest,
} from './daily.ts';
import {
  codeForDatabaseError,
  COOLDOWN_TAKEN_DATABASE_CODE,
  handleRefresh,
  OwnerCheck,
  readConfig,
  RefreshCode,
  runningWindowStart,
  StoreError,
  type Activity,
  type Claim,
  type DispatchRequest,
  type RefreshPorts,
  type RefreshTarget,
} from './refresh.ts';

const RUNNING_STATUS = 'running';
const FAILED_STATUS = 'failed';
const REFRESH_TRIGGER = 'refresh';

/** Postgres "unique_violation": the owner's day is already claimed. */
const DAY_TAKEN_DATABASE_CODE = '23505';

/** Daily runs read per look; a day holds one, or a few re-runs at most. */
const DAILY_RUNS_READ_LIMIT = 50;

/** A database client that acts as the caller, so the access rules apply. */
function clientFor(authorization: string): SupabaseClient | null {
  const url = Deno.env.get('SUPABASE_URL');
  const anonKey = Deno.env.get('SUPABASE_ANON_KEY');
  if (!url || !anonKey) return null;
  return createClient(url, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

async function checkOwner(client: SupabaseClient | null): Promise<OwnerCheck> {
  if (client === null) return OwnerCheck.Unavailable;
  const { data, error } = await client.rpc('is_app_owner');
  if (error !== null) {
    return codeForDatabaseError(error.code) === RefreshCode.NotSignedIn
      ? OwnerCheck.NotSignedIn
      : OwnerCheck.Unavailable;
  }
  return data === true ? OwnerCheck.Owner : OwnerCheck.NotOwner;
}

function firstDate(rows: unknown, column: string): Date | null {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const value: unknown = (rows[0] as Record<string, unknown>)[column];
  return typeof value === 'string' ? new Date(value) : null;
}

async function readActivity(client: SupabaseClient, now: Date): Promise<Activity> {
  const [running, requests] = await Promise.all([
    client
      .from('run_logs')
      .select('started_at')
      .eq('status', RUNNING_STATUS)
      .gte('started_at', runningWindowStart(now).toISOString())
      .order('started_at', { ascending: false })
      .limit(1),
    client
      .from('refresh_requests')
      .select('requested_at')
      .order('requested_at', { ascending: false })
      .limit(1),
  ]);
  const failed = running.error ?? requests.error;
  if (failed !== null) throw new StoreError(codeForDatabaseError(failed.code));
  return {
    runningSince: firstDate(running.data, 'started_at'),
    lastRequestAt: firstDate(requests.data, 'requested_at'),
  };
}

async function claimRequest(client: SupabaseClient, target: RefreshTarget): Promise<Claim | null> {
  const { data, error } = await client
    .from('refresh_requests')
    .insert({ target })
    .select('id')
    .single();
  if (error?.code === COOLDOWN_TAKEN_DATABASE_CODE) return null;
  if (error !== null) throw new StoreError(codeForDatabaseError(error.code));
  return { id: String((data as { id: unknown }).id) };
}

async function releaseRequest(client: SupabaseClient, claimed: Claim): Promise<void> {
  const { error } = await client.from('refresh_requests').delete().eq('id', claimed.id);
  if (error !== null) throw new StoreError(codeForDatabaseError(error.code));
}

async function send(request: DispatchRequest): Promise<number> {
  const response = await fetch(request.url, request.init);
  // The body is read and dropped: it is never logged or passed on.
  await response.body?.cancel();
  return response.status;
}

/** Structured log lines; the Edge runtime's console is its only log sink. */
function log(event: string, fields: Record<string, string | number | boolean | null>): void {
  console.info(JSON.stringify({ event, ...fields }));
}

function portsFor(request: Request): RefreshPorts {
  const client = clientFor(request.headers.get('Authorization') ?? '');
  const now = () => new Date();
  return {
    config: readConfig((name) => Deno.env.get(name)),
    dashboardOrigin: Deno.env.get('DASHBOARD_ORIGIN'),
    now,
    checkOwner: () => checkOwner(client),
    readActivity: async () => {
      if (client === null) throw new StoreError(RefreshCode.DatabaseUnavailable);
      return readActivity(client, now());
    },
    claimRequest: async (target) => {
      if (client === null) throw new StoreError(RefreshCode.DatabaseUnavailable);
      return claimRequest(client, target);
    },
    releaseRequest: async (claimed) => {
      if (client === null) throw new StoreError(RefreshCode.DatabaseUnavailable);
      return releaseRequest(client, claimed);
    },
    send,
    log,
  };
}

/**
 * A database client with the service key, for the scheduled path only: its
 * caller is the pg_cron job, never a person, and it has proved itself with
 * the shared key before this client is used.
 */
function serviceClient(): SupabaseClient | null {
  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  if (!url || !serviceKey) return null;
  return createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function storeFailure(code: string | undefined): StoreError {
  return new StoreError(codeForDatabaseError(code));
}

async function readSchedule(client: SupabaseClient): Promise<OwnerSchedule | null> {
  const { data, error } = await client
    .from('app_settings')
    .select('time_zone, daily_run_time')
    .eq('singleton', true)
    .limit(1);
  if (error !== null) throw storeFailure(error.code);
  if (!Array.isArray(data) || data.length === 0) return null;
  const row = data[0] as Record<string, unknown>;
  const { time_zone: timeZone, daily_run_time: runAt } = row;
  if (typeof timeZone !== 'string' || typeof runAt !== 'string') return null;
  return { timeZone, runAt };
}

async function readDailyRuns(client: SupabaseClient, since: Date): Promise<Date[]> {
  const { data, error } = await client
    .from('run_logs')
    .select('started_at')
    .neq('trigger', REFRESH_TRIGGER)
    .neq('status', FAILED_STATUS)
    .gte('started_at', since.toISOString())
    .order('started_at', { ascending: false })
    .limit(DAILY_RUNS_READ_LIMIT);
  if (error !== null) throw storeFailure(error.code);
  if (!Array.isArray(data)) return [];
  return data
    .map((row) => (row as Record<string, unknown>).started_at)
    .filter((value): value is string => typeof value === 'string')
    .map((value) => new Date(value));
}

async function claimDay(client: SupabaseClient, ownerDate: string): Promise<DayClaim | null> {
  const { data, error } = await client
    .from('daily_starts')
    .insert({ owner_date: ownerDate })
    .select('id')
    .single();
  if (error?.code === DAY_TAKEN_DATABASE_CODE) return null;
  if (error !== null) throw storeFailure(error.code);
  return { id: String((data as { id: unknown }).id) };
}

async function releaseDay(client: SupabaseClient, claimed: DayClaim): Promise<void> {
  const { error } = await client.from('daily_starts').delete().eq('id', claimed.id);
  if (error !== null) throw storeFailure(error.code);
}

async function fetchJson(request: ReadRequest): Promise<{ status: number; body: unknown }> {
  const response = await fetch(request.url, request.init);
  // The body is parsed here and only its shape is read; it is never logged.
  const body: unknown = await response.json().catch(() => null);
  return { status: response.status, body };
}

/** Runs one database call, or fails as "database unavailable" when there is no client. */
function withClient<T>(client: SupabaseClient | null, call: (client: SupabaseClient) => Promise<T>): Promise<T> {
  if (client === null) return Promise.reject(new StoreError(RefreshCode.DatabaseUnavailable));
  return call(client);
}

function dailyPorts(): DailyStartPorts {
  const client = serviceClient();
  return {
    config: readConfig((name) => Deno.env.get(name)),
    configuredKey: Deno.env.get('DAILY_START_KEY'),
    now: () => new Date(),
    readSchedule: () => withClient(client, readSchedule),
    readDailyRuns: (since) => withClient(client, (db) => readDailyRuns(db, since)),
    claimDay: (ownerDate) => withClient(client, (db) => claimDay(db, ownerDate)),
    releaseDay: (claimed) => withClient(client, (db) => releaseDay(db, claimed)),
    send,
    fetchJson,
    log,
  };
}

/** The scheduled path is told apart by its address, so the button never reaches it. */
function isDailyStart(request: Request): boolean {
  return new URL(request.url).pathname.endsWith(DAILY_START_PATH);
}

Deno.serve((request: Request) =>
  isDailyStart(request)
    ? handleDailyStart(request, dailyPorts())
    : handleRefresh(request, portsFor(request)),
);
