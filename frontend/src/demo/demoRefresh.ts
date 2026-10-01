import type { RunWithSteps } from '../api/schemas';
import { DEMO_REFRESH_SECONDS } from '../constants/dashboard';
import type { RunStep } from '../types/database';

/**
 * The demo's pretend "Refresh now": a quick run appears as "running" and
 * reads as finished once `DEMO_REFRESH_SECONDS` have passed on the demo's
 * clock. Nothing is scheduled; the finish is worked out on each read.
 */

const MILLISECONDS_PER_SECOND = 1_000;
const REFRESH_TRIGGER = 'refresh';
const REFRESH_ID_PREFIX = 'demo-refresh-';

/** A new, still-running refresh run starting at `now`. */
export function startedRefreshRun(sequence: number, now: Date): RunWithSteps {
  const stamp = now.toISOString();
  return {
    id: `${REFRESH_ID_PREFIX}${sequence}`,
    created_at: stamp,
    updated_at: stamp,
    started_at: stamp,
    finished_at: null,
    status: 'running',
    trigger: REFRESH_TRIGGER,
    run_step_logs: [],
  };
}

/** What the pretend refresh finds: a few new messages, no e-mail sent. */
const REFRESH_STEPS: readonly (readonly [step: RunStep, found: number, added: number])[] = [
  ['collect_linkedin', 3, 1],
  ['collect_email', 6, 2],
  ['assess', 3, 3],
];

function finishedSteps(run: RunWithSteps): RunWithSteps['run_step_logs'] {
  return REFRESH_STEPS.map(([step, found, added], index) => ({
    id: `${run.id}-s${index}`,
    created_at: run.started_at,
    updated_at: run.started_at,
    run_id: run.id,
    step,
    status: 'success',
    items_found: found,
    items_new: added,
    error_code: null,
    error_detail: null,
  }));
}

/** The run as it looks at `now`: still running, or finished with a few new messages. */
export function settledRun(run: RunWithSteps, now: Date): RunWithSteps {
  if (!run.id.startsWith(REFRESH_ID_PREFIX) || run.status !== 'running') return run;
  const finishAt =
    new Date(run.started_at).getTime() + DEMO_REFRESH_SECONDS * MILLISECONDS_PER_SECOND;
  if (now.getTime() < finishAt) return run;
  return {
    ...run,
    status: 'success',
    finished_at: new Date(finishAt).toISOString(),
    updated_at: new Date(finishAt).toISOString(),
    run_step_logs: finishedSteps(run),
  };
}

/** True while a pretend refresh has not finished yet. */
export function refreshIsRunning(runs: readonly RunWithSteps[], now: Date): boolean {
  return runs.some((run) => settledRun(run, now).status === 'running');
}
