import { useId } from 'react';
import * as copy from '../copy/en';
import { PEOPLE_SORTS, type PeopleSort } from '../domain/peopleView';

const SORT_LABELS: Record<PeopleSort, string> = {
  'last-contact': copy.sortLabels.lastContact,
  'due-date': copy.sortLabels.dueDate,
  name: copy.sortLabels.name,
};

interface SortSelectProps {
  value: PeopleSort;
  onChange: (next: PeopleSort) => void;
}

/** Chooses the order of the people list. */
export function SortSelect({ value, onChange }: SortSelectProps) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm font-medium text-ink-muted">
        {copy.home.sortLabel}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          const next = PEOPLE_SORTS.find((sort) => sort === event.target.value);
          if (next !== undefined) onChange(next);
        }}
        className="min-h-11 rounded-token-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
      >
        {PEOPLE_SORTS.map((sort) => (
          <option key={sort} value={sort}>
            {SORT_LABELS[sort]}
          </option>
        ))}
      </select>
    </div>
  );
}
