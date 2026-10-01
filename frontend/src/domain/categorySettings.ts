import type {
  Category,
  CategoryColour,
  CategoryKey,
  CategorySuggestion,
} from '../types/database';

/**
 * Rules for editing categories on the settings page. They mirror the checks
 * the database enforces, so the page can explain a limit before the database
 * has to refuse it. Pure: no fetching, no copy.
 */

/** The reserved category every profile has. It can never be changed or moved. */
export const RESERVED_CATEGORY_KEY: CategoryKey = 'unknown';

/** Keys a new category may never take: the reserved one and the "no filter" value. */
const FORBIDDEN_KEYS: readonly CategoryKey[] = [RESERVED_CATEGORY_KEY, 'all'];

/** At most this many categories may be in use, not counting the reserved one. */
export const MAX_ACTIVE_CATEGORIES = 8;

/** Longest name and group name the database accepts. */
export const MAX_LABEL_LENGTH = 40;

/** Longest "who belongs here" text the database accepts. */
export const MAX_DESCRIPTION_LENGTH = 1000;

/** Longest key the database accepts. */
const MAX_KEY_LENGTH = 31;

/** The owner's categories are numbered 10, 20, 30… so there is room between them. */
const SORT_STEP = 10;

/** Highest position an owner's category may have; the reserved one sits at 1000. */
const MAX_OWNER_SORT_ORDER = 999;

/** Every palette slot, in the order the colour picker shows them. */
export const CATEGORY_COLOURS = [
  'violet',
  'cyan',
  'orange',
  'pink',
  'indigo',
  'teal',
  'olive',
  'brown',
  'grey',
] as const satisfies readonly CategoryColour[];

/** Which way a category moves in the list. */
export enum MoveDirection {
  Up = 'up',
  Down = 'down',
}

/** A category's new position, as one update to send. */
export interface SortChange {
  key: CategoryKey;
  sort_order: number;
}

/** The fields the owner types when adding or editing a category. */
export interface CategoryDraft {
  label: string;
  group_label: string;
  description: string;
  colour: CategoryColour;
}

/** What is wrong with a draft, if anything; each maps to one sentence of copy. */
export enum DraftProblem {
  MissingName = 'missing_name',
  NameTooLong = 'name_too_long',
  DuplicateName = 'duplicate_name',
  MissingGroupName = 'missing_group_name',
  GroupNameTooLong = 'group_name_too_long',
  DuplicateGroupName = 'duplicate_group_name',
  MissingDescription = 'missing_description',
  DescriptionTooLong = 'description_too_long',
}

/**
 * The database's unique indexes on a category's names (migration 0015). When
 * a save is refused as a duplicate, the index it names says which name
 * clashed with a category the page had not loaded yet.
 */
export enum CategoryNameIndex {
  Label = 'categories_label_unique',
  GroupLabel = 'categories_group_label_unique',
}

const CLASH_PROBLEMS: ReadonlyMap<string, DraftProblem> = new Map([
  [CategoryNameIndex.Label, DraftProblem.DuplicateName],
  [CategoryNameIndex.GroupLabel, DraftProblem.DuplicateGroupName],
]);

/** The draft problem a refused save names, or null for any other rule. */
export function problemForIndex(constraint: string | null): DraftProblem | null {
  return constraint === null ? null : (CLASH_PROBLEMS.get(constraint) ?? null);
}

/** True for the reserved "not known" category. */
export function isReserved(category: Category): boolean {
  return category.key === RESERVED_CATEGORY_KEY;
}

/** The owner's categories in use, in order, without the reserved one. */
export function activeOwnCategories(categories: readonly Category[]): Category[] {
  return categories.filter((category) => category.archived_at === null && !isReserved(category));
}

/** The categories the owner has hidden, in order. */
export function hiddenCategories(categories: readonly Category[]): Category[] {
  return categories.filter((category) => category.archived_at !== null && !isReserved(category));
}

/** True while another category may be added or shown again. */
export function canAddCategory(categories: readonly Category[]): boolean {
  return activeOwnCategories(categories).length < MAX_ACTIVE_CATEGORIES;
}

/** The position for a new category: after every other one of the owner's. */
export function nextSortOrder(categories: readonly Category[]): number {
  const own = categories.filter((category) => !isReserved(category));
  const last = Math.max(0, ...own.map((category) => category.sort_order));
  return Math.min(last + SORT_STEP, MAX_OWNER_SORT_ORDER);
}

/** The first palette colour no category in use has yet, or grey when all are taken. */
export function firstFreeColour(categories: readonly Category[]): CategoryColour {
  const used = new Set(activeOwnCategories(categories).map((category) => category.colour));
  return CATEGORY_COLOURS.find((colour) => colour !== 'grey' && !used.has(colour)) ?? 'grey';
}

/**
 * The colour a suggestion is added with: its own, unless a category in use
 * already has that colour, in which case the first free one, so two
 * categories do not share a colour while another is still free.
 */
export function colourForSuggestion(
  suggestion: CategorySuggestion,
  categories: readonly Category[],
): CategoryColour {
  const taken = activeOwnCategories(categories).some(
    (category) => category.colour === suggestion.colour,
  );
  return taken ? firstFreeColour(categories) : suggestion.colour;
}

/** Suggestions whose key is not already a category, in use or hidden. */
export function suggestionsToOffer(
  suggestions: readonly CategorySuggestion[],
  categories: readonly Category[],
): CategorySuggestion[] {
  const taken = new Set(categories.map((category) => category.key));
  return suggestions.filter((suggestion) => !taken.has(suggestion.key));
}

/**
 * Moves one of the owner's categories a place up or down and numbers the list
 * 10, 20, 30… again. Returns only the positions that changed; an empty list
 * when the category is already at that end, or is not one of the owner's.
 */
export function moveCategory(
  categories: readonly Category[],
  key: CategoryKey,
  direction: MoveDirection,
): SortChange[] {
  const own = activeOwnCategories(categories);
  const from = own.findIndex((category) => category.key === key);
  const to = direction === MoveDirection.Up ? from - 1 : from + 1;
  if (from === -1 || to < 0 || to >= own.length) return [];

  const reordered = [...own];
  const [moved] = reordered.splice(from, 1);
  if (moved === undefined) return [];
  reordered.splice(to, 0, moved);

  return reordered
    .map((category, index) => ({ category, sort_order: (index + 1) * SORT_STEP }))
    .filter(({ category, sort_order }) => category.sort_order !== sort_order)
    .map(({ category, sort_order }) => ({ key: category.key, sort_order }));
}

/**
 * The group name suggested for a new category: its name with an "s", or the
 * name alone when the "s" would make it longer than a group name may be.
 */
export function suggestedGroupLabel(label: string): string {
  const trimmed = label.trim();
  if (trimmed === '') return '';
  const plural = `${trimmed}s`;
  return plural.length > MAX_LABEL_LENGTH ? trimmed : plural;
}

/** The form field each problem is about, so that field can be marked and focused. */
const PROBLEM_FIELDS: Record<DraftProblem, keyof CategoryDraft> = {
  [DraftProblem.MissingName]: 'label',
  [DraftProblem.NameTooLong]: 'label',
  [DraftProblem.DuplicateName]: 'label',
  [DraftProblem.MissingGroupName]: 'group_label',
  [DraftProblem.GroupNameTooLong]: 'group_label',
  [DraftProblem.DuplicateGroupName]: 'group_label',
  [DraftProblem.MissingDescription]: 'description',
  [DraftProblem.DescriptionTooLong]: 'description',
};

/** The field a problem is about, or null when there is none. */
export function problemField(problem: DraftProblem | null): keyof CategoryDraft | null {
  return problem === null ? null : PROBLEM_FIELDS[problem];
}

/** The draft with surrounding spaces taken off every text field. */
export function trimDraft(draft: CategoryDraft): CategoryDraft {
  return {
    label: draft.label.trim(),
    group_label: draft.group_label.trim(),
    description: draft.description.trim(),
    colour: draft.colour,
  };
}

/**
 * A name as it is compared for clashes: case, accents' composed forms and
 * runs of spaces do not matter, so "customer" and " Customer" are the same.
 */
export function comparableName(name: string): string {
  return name.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase();
}

/** True when one of `others` already has `name` in `field`, ignoring case. */
function nameIsTaken(
  name: string,
  field: 'label' | 'group_label',
  others: readonly Category[],
): boolean {
  const wanted = comparableName(name);
  return others.some((category) => comparableName(category[field]) === wanted);
}

/**
 * The first thing wrong with a draft, or null when it can be saved.
 *
 * @param others Every other category, hidden ones included (not the one being
 *   edited): two categories with the same name would show as two identical
 *   columns and filter buttons.
 */
export function findDraftProblem(
  draft: CategoryDraft,
  others: readonly Category[],
): DraftProblem | null {
  const { label, group_label, description } = trimDraft(draft);
  if (label === '') return DraftProblem.MissingName;
  if (label.length > MAX_LABEL_LENGTH) return DraftProblem.NameTooLong;
  if (nameIsTaken(label, 'label', others)) return DraftProblem.DuplicateName;
  if (group_label === '') return DraftProblem.MissingGroupName;
  if (group_label.length > MAX_LABEL_LENGTH) return DraftProblem.GroupNameTooLong;
  if (nameIsTaken(group_label, 'group_label', others)) return DraftProblem.DuplicateGroupName;
  if (description === '') return DraftProblem.MissingDescription;
  if (description.length > MAX_DESCRIPTION_LENGTH) return DraftProblem.DescriptionTooLong;
  return null;
}

/** Lower case, accents dropped, every run of other characters turned into one "_". */
function slugBase(name: string): string {
  const slug = name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  const startsWithLetter = /^[a-z]/.test(slug);
  return startsWithLetter ? slug : `c_${slug}`.replace(/_+$/, '');
}

/** `base` cut short enough to take `suffix`, never ending in "_". */
function withSuffix(base: string, suffix: string): string {
  const room = MAX_KEY_LENGTH - suffix.length;
  return `${base.slice(0, room).replace(/_+$/, '')}${suffix}`;
}

/**
 * The key for a new category, made from the name the owner typed: lower case,
 * letters and digits joined by "_", starting with a letter, at most 31
 * characters, and never a key that is taken or reserved ("all", "unknown") —
 * a clash gets "_2", "_3"… on the end.
 */
export function categoryKeyFromName(
  name: string,
  existingKeys: readonly CategoryKey[],
): CategoryKey {
  const taken = new Set([...existingKeys, ...FORBIDDEN_KEYS]);
  const base = withSuffix(slugBase(name), '');
  let candidate = base;
  for (let attempt = 2; taken.has(candidate); attempt += 1) {
    candidate = withSuffix(base, `_${attempt}`);
  }
  return candidate;
}
