import { FunctionsFetchError, FunctionsHttpError } from '@supabase/supabase-js';
import { z } from 'zod';
import {
  REFRESH_SERVER_CODES,
  watchStart,
  type RefreshClientCode,
  type RefreshOutcome,
  type RefreshTarget,
} from '../domain/refresh';
import { getSupabaseClient } from '../lib/supabaseClient';
import { logWarning } from '../lib/logger';
import { runQuery } from './client';
import { runLogRowSchema } from './schemas';
import type { RunLogRow } from '../types/database';

/** The Edge Function behind "Refresh now" (supabase/functions/refresh-now). */
export const REFRESH_FUNCTION_NAME = 'refresh-now';

/** The gateway's answer when no function of that name is deployed. */
const NOT_DEPLOYED_STATUS = 404;

export const refreshRunQueryKey = ['refresh-run'] as const;

const refreshReplySchema = z.object({
  code: z.enum(REFRESH_SERVER_CODES),
  target: z.enum(['github', 'claude_routine']).optional(),
  requested_at: z.string().datetime({ offset: true }).optional(),
  retry_after_seconds: z.number().int().nonnegative().optional(),
});

function refused(code: RefreshClientCode): RefreshOutcome {
  return { kind: 'refused', code, target: null, retryAfterSeconds: null };
}

function toOutcome(body: unknown): RefreshOutcome {
  const parsed = refreshReplySchema.safeParse(body);
  if (!parsed.success) {
    logWarning('refresh.unexpected_reply');
    return refused('unexpected');
  }
  const { code, target, requested_at: requestedAt, retry_after_seconds: retryAfter } = parsed.data;
  const knownTarget: RefreshTarget | null = target ?? null;
  if (code === 'started') {
    if (requestedAt === undefined) return refused('unexpected');
    return { kind: 'started', requestedAt: new Date(requestedAt), target: knownTarget };
  }
  return { kind: 'refused', code, target: knownTarget, retryAfterSeconds: retryAfter ?? null };
}

async function readRefusal(error: FunctionsHttpError): Promise<RefreshOutcome> {
  const response: unknown = error.context;
  if (!(response instanceof Response)) return refused('unexpected');
  if (response.status === NOT_DEPLOYED_STATUS) return refused('not_deployed');
  try {
    return toOutcome(await response.json());
  } catch (cause) {
    if (!(cause instanceof SyntaxError)) throw cause;
    logWarning('refresh.unreadable_reply', { status: response.status });
    return refused('unexpected');
  }
}

/** A request that got no answer: the browser is offline, or the function is missing. */
function unanswered(): RefreshOutcome {
  if (navigator.onLine === false) {
    logWarning('refresh.offline');
    return refused('unreachable');
  }
  logWarning('refresh.unanswered');
  return refused('unanswered');
}

/**
 * Asks the refresh service to start one quick extra run.
 *
 * Never throws for a refusal: every answer, including "the service is not
 * switched on" and "could not reach it", comes back as an outcome to show.
 */
export async function requestRefresh(): Promise<RefreshOutcome> {
  const result = await getSupabaseClient().functions.invoke<unknown>(REFRESH_FUNCTION_NAME, {
    method: 'POST',
  });
  // The client types its error loosely; narrow it here.
  const error: unknown = result.error;
  if (error === null) return toOutcome(result.data);
  if (error instanceof FunctionsHttpError) return readRefusal(error);
  if (error instanceof FunctionsFetchError) return unanswered();
  logWarning('refresh.relay_failed');
  return refused('unexpected');
}

const latestRunSchema = z.array(runLogRowSchema);

/** The newest run that started since a refresh was asked for, if any yet. */
export async function fetchRunSince(requestedAt: Date): Promise<RunLogRow | null> {
  const supabase = getSupabaseClient();
  const rows = await runQuery('refresh.run', latestRunSchema, () =>
    supabase
      .from('run_logs')
      .select('id, created_at, updated_at, started_at, finished_at, status, trigger')
      .gte('started_at', watchStart(requestedAt).toISOString())
      .order('started_at', { ascending: false })
      .limit(1),
  );
  return rows[0] ?? null;
}
