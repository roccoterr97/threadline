import * as copy from '../copy/en';

/** Why adding is switched off: eight categories are already in use. */
export function LimitNote() {
  return (
    <p className="rounded-token-md border border-line bg-neutral-soft p-3 text-sm text-ink">
      {copy.categorySettings.limitReached}
    </p>
  );
}
