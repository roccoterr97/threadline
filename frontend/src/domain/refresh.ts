import {
  REFRESH_FIRST_CHECK_MS,
  REFRESH_POLL_INTERVAL_MS,
  REFRESH_RUN_MATCH_SLACK_MS,
  REFRESH_WATCH_LIMIT_MINUTES,
} from '../constants/dashboard';
import type { RunLogRow, RunStatus } from '../types/database';

/**
 * The rules behind the "Refresh now" button: what the refresh service may
 * answer, and how far along a started refresh is.
 */

/**
 * Every code the `refresh-now` Edge Function answers with. A test checks this
 * list against the function itself, so the two cannot drift apart.
 */
export const REFRESH_SERVER_CODES = [
  'started',
  'method_not_allowed',
  'origin_not_allowed',
  'not_signed_in',
  'not_owner',
  'not_set_up',
  'already_running',
  'too_soon',
  'runner_auth_failed',
  'runner_not_found',
  'runner_rejected',
  'runner_rate_limited',
  'runner_unavailable',
  'database_unavailable',
] as const;

export type RefreshServerCode = (typeof REFRESH_SERVER_CODES)[number];

/**
 * Answers the dashboard works out itself, when the function gave none.
 *
 * - `not_deployed`: Supabase answered that no such function exists.
 * - `unanswered`: the request got no readable answer while the browser is
 *   online. A missing function answers without CORS headers, so the browser
 *   hides that 404 behind a network error; it is almost always this.
 * - `unreachable`: the browser itself is offline.
 */
export type RefreshClientCode = 'not_deployed' | 'unanswered' | 'unreachable' | 'unexpected';

/** Why a refresh did not start. */
export type RefreshRefusal = Exclude<RefreshServerCode, 'started'> | RefreshClientCode;

export type RefreshTarget = 'github' | 'claude_routine';

/** What asking for a refresh came to. */
export type RefreshOutcome =
  | { kind: 'started'; requestedAt: Date; target: RefreshTarget | null }
  | {
      kind: 'refused';
      code: RefreshRefusal;
      target: RefreshTarget | null;
      retryAfterSeconds: number | null;
    };

/** Everything the button and its status line need to show. */
export type RefreshStatus =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'waiting' }
  | { kind: 'finished'; runStatus: RunStatus }
  | { kind: 'timed_out' }
  | {
      kind: 'refused';
      code: RefreshRefusal;
      target: RefreshTarget | null;
      retryAfterMinutes: number | null;
    };

const MILLISECONDS_PER_MINUTE = 60_000;
const SECONDS_PER_MINUTE = 60;

/**
 * The earliest start time a run can have and still be the one this refresh
 * asked for. A little slack covers the gap between the function's clock and
 * the database's.
 */
export function watchStart(requestedAt: Date): Date {
  return new Date(requestedAt.getTime() - REFRESH_RUN_MATCH_SLACK_MS);
}

function watchIsOver(requestedAt: Date, now: Date): boolean {
  return now.getTime() - requestedAt.getTime() >= REFRESH_WATCH_LIMIT_MINUTES * MILLISECONDS_PER_MINUTE;
}

/**
 * How far along a started refresh is, given the newest run since it was asked
 * for. A run that has not finished within the watch limit is left to the run
 * history page.
 */
export function refreshProgress(
  run: RunLogRow | null,
  requestedAt: Date,
  now: Date,
): Extract<RefreshStatus, { kind: 'waiting' | 'finished' | 'timed_out' }> {
  if (run !== null && run.status !== 'running') return { kind: 'finished', runStatus: run.status };
  return watchIsOver(requestedAt, now) ? { kind: 'timed_out' } : { kind: 'waiting' };
}

/**
 * How long to wait before looking again, or false to stop. The first look is
 * soon, in case the run is quick; after that, every half minute.
 */
export function nextCheckDelay(checksDone: number, progressKind: RefreshStatus['kind']): number | false {
  if (progressKind !== 'waiting') return false;
  return checksDone <= 1 ? REFRESH_FIRST_CHECK_MS : REFRESH_POLL_INTERVAL_MS;
}

/** A refusal as the status line shows it, with the wait rounded up to minutes. */
export function refusalStatus(
  outcome: Extract<RefreshOutcome, { kind: 'refused' }>,
): Extract<RefreshStatus, { kind: 'refused' }> {
  const seconds = outcome.retryAfterSeconds;
  return {
    kind: 'refused',
    code: outcome.code,
    target: outcome.target,
    retryAfterMinutes: seconds === null ? null : Math.max(1, Math.ceil(seconds / SECONDS_PER_MINUTE)),
  };
}

/** True while the button should not start another refresh. */
export function refreshIsBusy(status: RefreshStatus): boolean {
  return status.kind === 'sending' || status.kind === 'waiting';
}
