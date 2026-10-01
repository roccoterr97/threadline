import type { Category, CategoryKey, PeopleOverviewRow } from '../types/database';

/**
 * Rules for the owner-defined categories. Pure: the list comes from the
 * database, and nothing here knows what any category means.
 */

/** Sorts a category the list does not know after every real one. */
const STRAY_SORT_ORDER = Number.MAX_SAFE_INTEGER;

/**
 * Stands in for a key the fetched list does not know. The foreign key should
 * make this impossible, but the screen must still show the person: it shows
 * the key itself, in grey.
 */
function strayCategory(key: CategoryKey): Category {
  return {
    key,
    label: key,
    group_label: key,
    description: '',
    colour: 'grey',
    sort_order: STRAY_SORT_ORDER,
    archived_at: null,
  };
}

/** True when the owner has retired this category. */
export function isArchived(category: Category): boolean {
  return category.archived_at !== null;
}

/** The category behind a key. Never fails: an unknown key gets a grey stand-in. */
export function categoryFor(categories: readonly Category[], key: CategoryKey): Category {
  return categories.find((category) => category.key === key) ?? strayCategory(key);
}

/**
 * The categories to show as filter chips and grid columns, in list order.
 *
 * Every live category is shown, even with nobody in it, so the grid keeps its
 * shape. An archived category, or a key the list does not know, is shown only
 * while someone on the list still has it — so every person always lands in
 * exactly one column.
 */
export function categoriesInUse(
  categories: readonly Category[],
  people: readonly PeopleOverviewRow[],
): Category[] {
  const used = new Set(people.map((person) => person.person_type));
  const known = new Set(categories.map((category) => category.key));
  const shown = categories.filter((category) => !isArchived(category) || used.has(category.key));
  const strays = [...used]
    .filter((key) => !known.has(key))
    .sort()
    .map(strayCategory);
  return [...shown, ...strays];
}

/**
 * The categories the correction form offers: every live one. The value already
 * saved is kept as a choice even if it has since been archived, so the form
 * never shows something other than what is stored.
 */
export function categoryChoices(
  categories: readonly Category[],
  current: CategoryKey | null,
): Category[] {
  const live = categories.filter((category) => !isArchived(category));
  if (current === null || live.some((category) => category.key === current)) return live;
  return [...live, categoryFor(categories, current)];
}
