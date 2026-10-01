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
  MissingGroupName = 'missing_group_name',
  GroupNameTooLong = 'group_name_too_long',
  MissingDescription = 'missing_description',
  DescriptionTooLong = 'description_too_long',
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

/** The group name suggested for a new category: its name with an "s". */
export function suggestedGroupLabel(label: string): string {
  const trimmed = label.trim();
  return trimmed === '' ? '' : `${trimmed}s`;
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

/** The first thing wrong with a draft, or null when it can be saved. */
export function findDraftProblem(draft: CategoryDraft): DraftProblem | null {
  const { label, group_label, description } = trimDraft(draft);
  if (label === '') return DraftProblem.MissingName;
  if (label.length > MAX_LABEL_LENGTH) return DraftProblem.NameTooLong;
  if (group_label === '') return DraftProblem.MissingGroupName;
  if (group_label.length > MAX_LABEL_LENGTH) return DraftProblem.GroupNameTooLong;
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
