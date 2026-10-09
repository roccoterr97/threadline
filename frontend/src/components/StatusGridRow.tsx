import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { CountsByType } from '../domain/counters';
import { ANY, type StatusKey, type TypeFilter } from '../domain/peopleView';
import type { Category } from '../types/database';

/** A grid row's status, or every status for the totals line. */
export type GridStatus = StatusKey | typeof ANY;

/** The address that shows exactly the people behind one count. */
export type GridLinkFor = (type: TypeFilter, status: GridStatus) => string;

const CELL = 'px-1 text-right tabular-nums sm:px-3';
/** A count's box is as big as a thumb needs; a zero gets the same box so the rows line up. */
const COUNT_BOX = 'inline-flex min-h-11 min-w-11 items-center justify-center';
/**
 * The status column stays put while the counts scroll sideways on a narrow
 * screen. An inset line marks its edge, since a collapsed border would scroll away.
 */
export const STICKY_COLUMN =
  'sticky left-0 bg-surface shadow-[inset_-1px_0_0_var(--tracker-border)]';
const ROW_HEAD = `${STICKY_COLUMN} px-1 py-1 text-left text-ink sm:px-3`;

interface CountLinkProps {
  count: number;
  type: TypeFilter;
  typeText: string;
  status: GridStatus;
  statusText: string;
  linkFor: GridLinkFor;
}

/** A count that opens the people behind it; zero stays plain text. */
function CountLink({ count, type, typeText, status, statusText, linkFor }: CountLinkProps) {
  if (count === 0) return <span className={`${COUNT_BOX} text-ink-muted`}>0</span>;
  return (
    <Link
      to={linkFor(type, status)}
      aria-label={copy.home.grid.cellLabel(count, typeText, statusText)}
      className={`${COUNT_BOX} rounded-token-sm font-medium text-accent underline underline-offset-2`}
    >
      {count}
    </Link>
  );
}

interface StatusGridRowProps {
  heading: string;
  status: GridStatus;
  counts: CountsByType;
  total: number;
  columns: readonly Category[];
  linkFor: GridLinkFor;
  strong?: boolean;
}

/** One line of counts: a count per category, then the line's total. */
export function StatusGridRow({
  heading,
  status,
  counts,
  total,
  columns,
  linkFor,
  strong = false,
}: StatusGridRowProps) {
  const weight = strong ? 'font-semibold' : 'font-normal';
  const statusText = status === ANY ? copy.filterLabels.anyStatus : heading;
  return (
    <tr className={strong ? undefined : 'border-b border-line'}>
      <th scope="row" className={`${ROW_HEAD} ${weight}`}>
        {heading}
      </th>
      {columns.map((category) => (
        <td key={category.key} className={`${CELL} ${strong ? 'font-semibold' : ''}`}>
          <CountLink
            count={counts[category.key] ?? 0}
            type={category.key}
            typeText={category.group_label}
            status={status}
            statusText={statusText}
            linkFor={linkFor}
          />
        </td>
      ))}
      <td className={`${CELL} font-semibold`}>
        <CountLink
          count={total}
          type={ANY}
          typeText={copy.filterLabels.everyone}
          status={status}
          statusText={statusText}
          linkFor={linkFor}
        />
      </td>
    </tr>
  );
}
