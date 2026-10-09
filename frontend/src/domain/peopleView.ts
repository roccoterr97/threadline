import { PEOPLE_MAX_ROWS } from '../constants/dashboard';
import type { CategoryKey, ContactStatus, PeopleOverviewRow, WaitingOn } from '../types/database';

/** Every status the assistant can give, in the order a conversation moves. */
export const CONTACT_STATUSES = [
  'contacted_no_reply',
  'in_conversation',
  'meeting_planned',
  'in_process',
  'gone_quiet',
  'closed',
] as const satisfies readonly ContactStatus[];

/** Stands for "the assistant has not looked at this person yet" (no status). */
export const NOT_ASSESSED = 'none';

/** A status, or the absence of one. Used by the status filter and the grid. */
export type StatusKey = ContactStatus | typeof NOT_ASSESSED;

/** The status filter value that means "any of the running statuses". */
export const ACTIVE = 'active';

/** Statuses that mean a conversation is genuinely running. */
export const ACTIVE_STATUSES = [
  'in_conversation',
  'meeting_planned',
  'in_process',
] as const satisfies readonly ContactStatus[];

/** True when the status means the conversation is still running. */
export function isActiveStatus(status: ContactStatus | null): boolean {
  return ACTIVE_STATUSES.some((active) => active === status);
}

/** The value every filter takes when it narrows nothing. */
export const ANY = 'all';

/**
 * The type filter: `ANY`, or the key of one category. Categories are data, so
 * this is a plain string; `readPeopleView` only lets through keys it was given.
 */
export type TypeFilter = CategoryKey;

export const STATUS_FILTERS = [ANY, ACTIVE, ...CONTACT_STATUSES, NOT_ASSESSED] as const;
export type StatusFilter = (typeof STATUS_FILTERS)[number];

export const WAITING_FILTERS = [ANY, 'me', 'them', 'nobody'] as const satisfies readonly (
  | typeof ANY
  | WaitingOn
)[];
export type WaitingFilter = (typeof WAITING_FILTERS)[number];

/** "overdue" is a reply the owner owes; "chase" is a nudge the owner could send. */
export const DUE_FILTERS = [ANY, 'overdue', 'chase'] as const;
export type DueFilter = (typeof DUE_FILTERS)[number];

/** The sort options on the home page. */
export const PEOPLE_SORTS = ['last-contact', 'due-date', 'name'] as const;
export type PeopleSort = (typeof PEOPLE_SORTS)[number];

/** The four filters on the home page. They combine: a row must match all of them. */
export interface PeopleFilters {
  type: TypeFilter;
  status: StatusFilter;
  waiting: WaitingFilter;
  due: DueFilter;
}

/** Everything that shapes the people list. Kept in the URL so a reload survives. */
export interface PeopleView extends PeopleFilters {
  sort: PeopleSort;
}

export const DEFAULT_FILTERS: PeopleFilters = { type: ANY, status: ANY, waiting: ANY, due: ANY };
export const DEFAULT_SORT: PeopleSort = 'last-contact';
export const DEFAULT_VIEW: PeopleView = { ...DEFAULT_FILTERS, sort: DEFAULT_SORT };

export const TYPE_PARAM = 'type';
export const STATUS_PARAM = 'status';
export const WAITING_PARAM = 'waiting';
export const DUE_PARAM = 'due';
export const SORT_PARAM = 'sort';

/** Reads one closed-list parameter, or returns `fallback` for missing or junk input. */
export function readChoice<T extends string>(
  params: URLSearchParams,
  name: string,
  options: readonly T[],
  fallback: T,
): T {
  const raw = params.get(name);
  return options.find((option) => option === raw) ?? fallback;
}

/**
 * Reads the four filters out of the URL, falling back to "any" for junk input.
 *
 * @param typeKeys The category keys the type filter may take right now. Any
 *   other `type` in the address — a category that no longer exists, or one
 *   not loaded yet — is ignored and every type is shown.
 */
export function readPeopleFilters(
  params: URLSearchParams,
  typeKeys: readonly CategoryKey[],
): PeopleFilters {
  return {
    type: readChoice(params, TYPE_PARAM, [ANY, ...typeKeys], ANY),
    status: readChoice(params, STATUS_PARAM, STATUS_FILTERS, ANY),
    waiting: readChoice(params, WAITING_PARAM, WAITING_FILTERS, ANY),
    due: readChoice(params, DUE_PARAM, DUE_FILTERS, ANY),
  };
}

/**
 * Reads the view out of the URL, falling back to the defaults for junk input.
 *
 * @param typeKeys The category keys the type filter may take right now, as
 *   `readPeopleFilters` takes them.
 */
export function readPeopleView(
  params: URLSearchParams,
  typeKeys: readonly CategoryKey[],
): PeopleView {
  return {
    ...readPeopleFilters(params, typeKeys),
    sort: readChoice(params, SORT_PARAM, PEOPLE_SORTS, DEFAULT_SORT),
  };
}

/** Writes the filters into a fresh URL query. Filters that narrow nothing are left out. */
export function writePeopleFilters(filters: PeopleFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.type !== ANY) params.set(TYPE_PARAM, filters.type);
  if (filters.status !== ANY) params.set(STATUS_PARAM, filters.status);
  if (filters.waiting !== ANY) params.set(WAITING_PARAM, filters.waiting);
  if (filters.due !== ANY) params.set(DUE_PARAM, filters.due);
  return params;
}

/**
 * Writes the view back into the URL. Defaults are left out so the plain address
 * stays clean and shareable.
 */
export function writePeopleView(view: PeopleView): URLSearchParams {
  const params = writePeopleFilters(view);
  if (view.sort !== DEFAULT_SORT) params.set(SORT_PARAM, view.sort);
  return params;
}

/** The same view with every filter cleared; the chosen order is kept. */
export function clearFilters(view: PeopleView): PeopleView {
  return { ...DEFAULT_FILTERS, sort: view.sort };
}

/** The status a row is counted and filtered under. */
export function statusKeyOf(row: PeopleOverviewRow): StatusKey {
  return row.status ?? NOT_ASSESSED;
}

function matchesDue(row: PeopleOverviewRow, due: DueFilter): boolean {
  switch (due) {
    case ANY:
      return true;
    case 'overdue':
      return row.is_overdue;
    case 'chase':
      return row.is_chase_due;
  }
}

function matchesStatus(row: PeopleOverviewRow, status: StatusFilter): boolean {
  if (status === ANY) return true;
  if (status === ACTIVE) return isActiveStatus(row.status);
  return statusKeyOf(row) === status;
}

/** True when the row passes every filter. */
export function matchesFilters(row: PeopleOverviewRow, filters: PeopleFilters): boolean {
  if (filters.type !== ANY && row.person_type !== filters.type) return false;
  if (!matchesStatus(row, filters.status)) return false;
  if (filters.waiting !== ANY && row.waiting_on !== filters.waiting) return false;
  return matchesDue(row, filters.due);
}

/** Sorts missing values last, whichever direction the column runs in. */
function compareNullableText(a: string | null, b: string | null, newestFirst: boolean): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return newestFirst ? b.localeCompare(a) : a.localeCompare(b);
}

function comparePeople(a: PeopleOverviewRow, b: PeopleOverviewRow, sort: PeopleSort): number {
  switch (sort) {
    case 'last-contact':
      return compareNullableText(a.last_contact_at, b.last_contact_at, true);
    case 'due-date':
      return compareNullableText(a.due_date, b.due_date, false);
    case 'name':
      return a.full_name.localeCompare(b.full_name);
  }
}

/** Applies every filter and the sort. Pure — the caller owns the fetching. */
export function applyPeopleView(
  people: readonly PeopleOverviewRow[],
  view: PeopleView,
): PeopleOverviewRow[] {
  return people
    .filter((row) => matchesFilters(row, view))
    .sort((a, b) => comparePeople(a, b, view.sort));
}

/**
 * True when the people list was cut short at the safety cap, so older people
 * are missing and every count built from it may be too low.
 */
export function peopleListIsCut(shown: number): boolean {
  return shown >= PEOPLE_MAX_ROWS;
}
