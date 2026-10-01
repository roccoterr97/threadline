import * as copy from '../copy/en';

interface ReviewCountProps {
  count: number;
  /** Extra classes for where the badge sits, e.g. pinned to an icon's corner. */
  className?: string;
}

/**
 * How many questions are waiting, as a small badge on the "To review" link.
 *
 * Screen readers hear a full sentence instead of a bare number. Nothing is
 * drawn when there is nothing to answer.
 */
export function ReviewCount({ count, className = '' }: ReviewCountProps) {
  if (count <= 0) return null;
  return (
    <span
      className={`rounded-token-sm bg-warn-soft px-1.5 py-0.5 text-xs leading-none font-semibold text-warn ${className}`}
    >
      <span className="sr-only">{copy.nav.reviewCountLabel(count)}</span>
      <span aria-hidden="true">{count}</span>
    </span>
  );
}
