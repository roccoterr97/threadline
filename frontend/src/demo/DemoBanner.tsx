import * as copy from '../copy/en';

/** Where a visitor who liked the demo learns to set up their own copy: the easy way first. */
export const SETUP_GUIDE_URL =
  'https://github.com/roccoterr97/threadline/blob/main/docs/setup-with-claude.md';

/** The strip across the top of every demo page, so nobody mistakes it for real data. */
export function DemoBanner() {
  return (
    <div
      role="note"
      className="bg-accent px-4 py-2 text-center text-sm font-medium text-accent-fg"
    >
      <span>{copy.demo.notice}</span>{' '}
      <a
        href={SETUP_GUIDE_URL}
        target="_blank"
        rel="noreferrer"
        className="whitespace-nowrap underline underline-offset-2"
      >
        {copy.demo.setupLink}
      </a>
    </div>
  );
}
