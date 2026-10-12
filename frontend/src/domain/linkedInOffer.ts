import type { RunLogRow, RunStep, RunStepLogRow } from '../types/database';

/** The part of a run the LinkedIn offer looks at: when, how it ended, and its steps. */
type RunWithStepNames = Pick<RunLogRow, 'status' | 'started_at'> & {
  run_step_logs: readonly Pick<RunStepLogRow, 'step'>[];
};

/** The steps that read a source. The mailbox one is always there: a mailbox is required. */
const COLLECT_STEPS: ReadonlySet<RunStep> = new Set([
  'collect_linkedin',
  'collect_email',
  'collect_calendar',
]);

/**
 * Whether the daily run does not read LinkedIn, so the dashboard may offer to add it.
 *
 * A run records a step only for a source that is set up, so the newest
 * finished run that read any source tells: without a `collect_linkedin` step,
 * LinkedIn is not connected. Until such a run exists nothing is known, and
 * nothing is offered. A run still going is left out, because its sources are
 * recorded one by one.
 *
 * @param runs Recent runs with their steps, in any order.
 */
export function linkedInMissing(runs: readonly RunWithStepNames[]): boolean {
  const newest = [...runs]
    .filter((run) => run.status !== 'running')
    .filter((run) => run.run_step_logs.some((step) => COLLECT_STEPS.has(step.step)))
    .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))[0];
  if (newest === undefined) return false;
  return !newest.run_step_logs.some((step) => step.step === 'collect_linkedin');
}
