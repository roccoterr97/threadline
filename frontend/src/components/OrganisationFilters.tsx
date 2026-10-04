import * as copy from '../copy/en';
import {
  ORGANISATION_SORTS,
  type OrganisationSort,
  type OrganisationsView,
} from '../domain/organisations';
import type { StatusLabels } from '../domain/vocabulary';
import type { Category } from '../types/database';
import { FilterControls } from './FilterControls';
import { FilterSelect } from './FilterSelect';

const SORT_LABELS: Record<OrganisationSort, string> = {
  attention: copy.organisations.sortLabels.attention,
  'last-contact': copy.sortLabels.lastContact,
  name: copy.sortLabels.name,
  people: copy.organisations.sortLabels.people,
};

interface OrganisationFiltersProps {
  view: OrganisationsView;
  /** The categories offered as chips. */
  categories: readonly Category[];
  statusLabels: StatusLabels;
  onChange: (next: OrganisationsView) => void;
}

/**
 * Everything that narrows or orders the organisations list: the People
 * page's own filters, and the orders that make sense for organisations.
 */
export function OrganisationFilters({
  view,
  categories,
  statusLabels,
  onChange,
}: OrganisationFiltersProps) {
  return (
    <FilterControls
      view={view}
      categories={categories}
      statusLabels={statusLabels}
      onChange={onChange}
    >
      <FilterSelect
        label={copy.home.sortLabel}
        value={view.sort}
        options={ORGANISATION_SORTS}
        labels={SORT_LABELS}
        onChange={(sort) => {
          onChange({ ...view, sort });
        }}
      />
    </FilterControls>
  );
}
