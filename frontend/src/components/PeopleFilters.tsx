import type { PeopleView } from '../domain/peopleView';
import type { StatusLabels } from '../domain/vocabulary';
import type { Category } from '../types/database';
import { FilterControls } from './FilterControls';
import { SortSelect } from './SortSelect';

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
    <FilterControls
      view={view}
      categories={categories}
      statusLabels={statusLabels}
      onChange={onChange}
    >
      <SortSelect
        value={view.sort}
        onChange={(sort) => {
          onChange({ ...view, sort });
        }}
      />
    </FilterControls>
  );
}
