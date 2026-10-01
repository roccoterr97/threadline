/**
 * Supabase Edge Function "refresh-now": the dashboard's "Refresh now" button.
 *
 * It checks that the caller is the dashboard's owner, refuses while a run is
 * going or right after the previous refresh, claims the cool-down in the
 * database, then asks the configured runner (a GitHub Actions workflow, or a
 * Claude cloud routine) for one quick extra run. The runner's key lives only
 * in this function's secrets.
 *
 * This file only connects `refresh.ts` to Deno and the database; every
 * decision is made (and tested) there. Setup: docs/refresh-now.md.
 */
import { createClient, type SupabaseClient } from 'npm:@supabase/supabase-js@2';
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

Deno.serve((request: Request) => handleRefresh(request, portsFor(request)));
