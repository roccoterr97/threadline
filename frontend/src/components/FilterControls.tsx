import type { ReactNode } from 'react';
import * as copy from '../copy/en';
import {
  DUE_FILTERS,
  STATUS_FILTERS,
  WAITING_FILTERS,
  type DueFilter,
  type PeopleFilters,
  type StatusFilter,
  type WaitingFilter,
} from '../domain/peopleView';
import type { StatusLabels } from '../domain/vocabulary';
import type { Category } from '../types/database';
import { FilterChips } from './FilterChips';
import { FilterSelect } from './FilterSelect';

function statusFilterLabels(statusLabels: StatusLabels): Record<StatusFilter, string> {
  return {
    all: copy.filterLabels.anyStatus,
    active: copy.filterLabels.active,
    ...statusLabels,
    none: copy.values.notAssessed,
  };
}

const WAITING_FILTER_LABELS: Record<WaitingFilter, string> = {
  all: copy.filterLabels.anyone,
  ...copy.waitingOnLabels,
};

const DUE_FILTER_LABELS: Record<DueFilter, string> = {
  all: copy.filterLabels.anyDate,
  overdue: copy.filterLabels.overdue,
  chase: copy.filterLabels.chase,
};

interface FilterControlsProps<View extends PeopleFilters> {
  /** The view on screen: the four filters, plus whatever else the page keeps with them. */
  view: View;
  /** The categories offered as chips. */
  categories: readonly Category[];
  statusLabels: StatusLabels;
  onChange: (next: View) => void;
  /** The control that picks the order, shown in the same row as the filters. */
  children: ReactNode;
}

/**
 * The filters the People page and the organisations page share: the type
 * chips, then the status, waiting-on and due filters, with the page's own
 * sort control beside them. The filters combine.
 */
export function FilterControls<View extends PeopleFilters>({
  view,
  categories,
  statusLabels,
  onChange,
  children,
}: FilterControlsProps<View>) {
  return (
    <div className="flex flex-col gap-3">
      <FilterChips
        value={view.type}
        categories={categories}
        onChange={(type) => {
          onChange({ ...view, type });
        }}
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-6">
        <FilterSelect
          label={copy.home.statusFilterLabel}
          value={view.status}
          options={STATUS_FILTERS}
          labels={statusFilterLabels(statusLabels)}
          onChange={(status) => {
            onChange({ ...view, status });
          }}
        />
        <FilterSelect
          label={copy.home.waitingFilterLabel}
          value={view.waiting}
          options={WAITING_FILTERS}
          labels={WAITING_FILTER_LABELS}
          onChange={(waiting) => {
            onChange({ ...view, waiting });
          }}
        />
        <FilterSelect
          label={copy.home.dueFilterLabel}
          value={view.due}
          options={DUE_FILTERS}
          labels={DUE_FILTER_LABELS}
          onChange={(due) => {
            onChange({ ...view, due });
          }}
        />
        {children}
      </div>
    </div>
  );
}
