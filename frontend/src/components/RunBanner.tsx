import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { RunHealth } from '../domain/runHealth';
import type { Clock } from '../lib/clock';
import { formatRelative } from '../lib/format';

interface RunBannerProps {
  health: RunHealth;
  clock: Clock;
}

function warningText(health: RunHealth): string | null {
  switch (health.kind) {
    case 'ok':
      return null;
    case 'failed':
      return copy.banner.lastRunFailed;
    case 'stale':
      return copy.banner.lastRunStale;
    case 'never':
      return copy.banner.noRunYet;
  }
}

function lastUpdatedText(health: RunHealth, clock: Clock): string | null {
  if (health.kind === 'ok' || health.kind === 'stale') {
    return copy.banner.updatedAt(formatRelative(health.lastSuccessAt, clock));
  }
  return null;
}

/**
 * Tells the owner whether what is on screen is up to date.
 *
 * A problem is an alert with a link to the run history; a healthy run is just
 * one quiet line of text.
 */
export function RunBanner({ health, clock }: RunBannerProps) {
  const warning = warningText(health);
  const updated = lastUpdatedText(health, clock);

  if (warning === null) {
    return <p className="text-sm text-ink-muted">{updated}</p>;
  }

  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-token-lg border border-warn bg-warn-soft p-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-warn">
        <span className="font-semibold">{warning}</span>
        {updated !== null && <span className="ml-1 text-ink-muted">{updated}.</span>}
      </p>
      <Link
        to="/runs"
        className="shrink-0 font-medium text-accent underline underline-offset-2"
      >
        {copy.banner.seeRuns}
      </Link>
    </div>
  );
}
