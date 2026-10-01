import * as copy from '../copy/en';
import {
  DUE_FILTERS,
  STATUS_FILTERS,
  WAITING_FILTERS,
  type DueFilter,
  type PeopleView,
  type StatusFilter,
  type WaitingFilter,
} from '../domain/peopleView';
import type { StatusLabels } from '../domain/vocabulary';
import type { Category } from '../types/database';
import { FilterChips } from './FilterChips';
import { FilterSelect } from './FilterSelect';
import { SortSelect } from './SortSelect';

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

interface PeopleFiltersProps {
  view: PeopleView;
  /** The categories offered as chips. */
  categories: readonly Category[];
  statusLabels: StatusLabels;
  onChange: (next: PeopleView) => void;
}

/**
 * Everything that narrows or orders the people list: the type chips, the
 * status, waiting-on and due filters, and the sort. The filters combine.
 */
export function PeopleFilters({
  view,
  categories,
  statusLabels,
  onChange,
}: PeopleFiltersProps) {
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
        <SortSelect
          value={view.sort}
          onChange={(sort) => {
            onChange({ ...view, sort });
          }}
        />
      </div>
    </div>
  );
}
