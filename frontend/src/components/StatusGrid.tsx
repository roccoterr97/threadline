import { useId } from 'react';
import * as copy from '../copy/en';
import type { StatusGrid as StatusGridCounts } from '../domain/counters';
import { ANY, NOT_ASSESSED, type StatusKey } from '../domain/peopleView';
import type { StatusLabels } from '../domain/vocabulary';
import { STICKY_COLUMN, StatusGridRow, type GridLinkFor } from './StatusGridRow';
import { TypeDot } from './TypeDot';

interface StatusGridProps {
  grid: StatusGridCounts;
  statusLabels: StatusLabels;
  linkFor: GridLinkFor;
}

const HEAD = 'px-1 py-2 text-right text-xs font-semibold text-ink-muted sm:px-3 sm:text-sm';

/**
 * How many people of each category sit in each status, at a glance.
 *
 * Statuses run down the side and categories across the top. A profile may have
 * up to nine categories, which cannot all fit a phone, so the grid scrolls
 * sideways inside its own frame (the page itself never does) and the status
 * names stay pinned on the left. Every non-zero count links to its people.
 */
export function StatusGrid({ grid, statusLabels, linkFor }: StatusGridProps) {
  const captionId = useId();
  const statusLabel = (status: StatusKey) =>
    status === NOT_ASSESSED ? copy.values.notAssessed : statusLabels[status];

  return (
    <div className="rounded-token-lg border border-line bg-surface shadow-card">
      {/* Outside the scrolling frame, so the title stays in view while the counts scroll. */}
      <h2 id={captionId} className="px-3 pt-3 pb-1 text-base font-semibold text-ink">
        {copy.home.grid.caption}
      </h2>
      <div className="overflow-x-auto">
        <table aria-labelledby={captionId} className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className={`${HEAD} ${STICKY_COLUMN} text-left`}>
                {copy.home.grid.statusColumn}
              </th>
              {grid.columns.map((category) => (
                <th key={category.key} scope="col" className={HEAD}>
                  <span className="inline-flex items-center justify-end gap-1">
                    <TypeDot colour={category.colour} />
                    {category.group_label}
                  </span>
                </th>
              ))}
              <th scope="col" className={HEAD}>
                {copy.home.grid.total}
              </th>
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((row) => (
              <StatusGridRow
                key={row.status}
                heading={statusLabel(row.status)}
                status={row.status}
                counts={row.counts}
                total={row.total}
                columns={grid.columns}
                linkFor={linkFor}
              />
            ))}
          </tbody>
          <tfoot>
            <StatusGridRow
              heading={copy.home.grid.total}
              status={ANY}
              counts={grid.columnTotals}
              total={grid.total}
              columns={grid.columns}
              linkFor={linkFor}
              strong
            />
          </tfoot>
        </table>
      </div>
    </div>
  );
}
