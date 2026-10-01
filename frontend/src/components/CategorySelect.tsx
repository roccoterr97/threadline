import * as copy from '../copy/en';
import { categoryChoices } from '../domain/categories';
import type { Category, CategoryKey } from '../types/database';
import { OverrideSelect } from './OverrideSelect';

interface CategorySelectProps {
  categories: readonly Category[];
  /** The category saved in the correction now, offered even if since archived. */
  saved: CategoryKey | null;
  /** Null means "leave it to the assistant". */
  value: CategoryKey | null;
  onChange: (next: CategoryKey | null) => void;
}

/** The correction form's category field: every live category, by its name. */
export function CategorySelect({ categories, saved, value, onChange }: CategorySelectProps) {
  const choices = categoryChoices(categories, saved);
  const labels = Object.fromEntries(choices.map((category) => [category.key, category.label]));
  return (
    <OverrideSelect
      label={copy.override.personTypeLabel}
      value={value}
      options={choices.map((category) => category.key)}
      labels={labels}
      onChange={onChange}
    />
  );
}
