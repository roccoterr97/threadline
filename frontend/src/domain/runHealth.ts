import { STALE_RUN_HOURS } from '../constants/dashboard';
import type { Clock } from '../lib/clock';
import type { RunLogRow } from '../types/database';

/** What, if anything, the home page should warn about. */
export type RunHealth =
  | { kind: 'ok'; lastSuccessAt: Date }
  | { kind: 'failed'; lastRunAt: Date }
  | { kind: 'stale'; lastSuccessAt: Date }
  | { kind: 'never' };

const MILLISECONDS_PER_HOUR = 3_600_000;

function runTime(run: RunLogRow): number {
  return new Date(run.finished_at ?? run.started_at).getTime();
}

/** Newest first, by the time the run finished (or started, if it still runs). */
function newestFirst(runs: readonly RunLogRow[]): RunLogRow[] {
  return [...runs].sort((a, b) => runTime(b) - runTime(a));
}

/**
 * Decides whether to warn the owner that the list may be out of date.
 *
 * The rules, in order:
 * 1. No run at all -> "never".
 * 2. The newest finished run failed -> "failed".
 * 3. The newest successful run is older than `STALE_RUN_HOURS` -> "stale".
 * 4. Otherwise -> "ok".
 *
 * A run still in progress is ignored: it has not told us anything yet.
 *
 * @param runs Recent runs, in any order.
 * @param clock Injected so the rule is testable at a fixed moment.
 */
export function assessRunHealth(runs: readonly RunLogRow[], clock: Clock): RunHealth {
  const settled = newestFirst(runs).filter((run) => run.status !== 'running');
  const newest = settled[0];
  if (newest === undefined) return { kind: 'never' };

  if (newest.status === 'failed') {
    return { kind: 'failed', lastRunAt: new Date(runTime(newest)) };
  }

  const lastGood = settled.find((run) => run.status === 'success' || run.status === 'partial');
  if (lastGood === undefined) return { kind: 'never' };

  const lastSuccessAt = new Date(runTime(lastGood));
  const ageHours = (clock.now().getTime() - lastSuccessAt.getTime()) / MILLISECONDS_PER_HOUR;
  if (ageHours > STALE_RUN_HOURS) return { kind: 'stale', lastSuccessAt };

  return { kind: 'ok', lastSuccessAt };
}
