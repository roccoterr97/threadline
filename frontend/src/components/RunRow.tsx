import type { RunWithSteps } from '../api/schemas';
import * as copy from '../copy/en';
import {
  describeStepCounts,
  explainRunError,
  explainRunTrigger,
  formatDateTime,
  formatDuration,
} from '../lib/format';
import type { RunStatus } from '../types/database';
import { Badge, type BadgeTone } from './Badge';

const STATUS_TONES: Record<RunStatus, BadgeTone> = {
  running: 'calm',
  success: 'positive',
  partial: 'warn',
  failed: 'danger',
};

interface RunRowProps {
  run: RunWithSteps;
}

/** One automatic update: when it ran, and how each of its steps went. */
export function RunRow({ run }: RunRowProps) {
  return (
    <li className="rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          tone={STATUS_TONES[run.status]}
          label={copy.runStatusLabels[run.status]}
          description="Result:"
        />
        <time dateTime={run.started_at} className="text-sm text-ink-muted">
          {copy.runs.startedAt} {formatDateTime(run.started_at)}
        </time>
        <span className="text-sm text-ink-muted">
          {copy.runs.duration} {formatDuration(run.started_at, run.finished_at)}
        </span>
        <span className="text-sm text-ink-muted">
          {copy.runs.trigger} {explainRunTrigger(run.trigger)}
        </span>
      </div>

      <h2 className="sr-only">{copy.runs.stepsTitle}</h2>
      <ul className="mt-3 flex list-none flex-col gap-2 p-0">
        {run.run_step_logs.map((step) => {
          const problem = explainRunError(step.error_code);
          return (
            <li key={step.id} className="flex flex-col gap-1 border-t border-line pt-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-ink">{copy.runStepLabels[step.step]}</span>
                <Badge
                  tone={STATUS_TONES[step.status]}
                  label={copy.runStatusLabels[step.status]}
                  description="Result:"
                />
                {describeStepCounts(step).map((count) => (
                  <span key={count} className="text-sm text-ink-muted">
                    {count}
                  </span>
                ))}
              </div>
              {problem !== null && <p className="text-sm text-danger">{problem}</p>}
            </li>
          );
        })}
      </ul>
    </li>
  );
}
