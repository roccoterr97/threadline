import type { CategoryKey, PeopleOverviewRow } from '../types/database';
import { countPeople, type PeopleCounters } from './counters';
import {
  applyPeopleView,
  DEFAULT_FILTERS,
  DEFAULT_VIEW,
  matchesFilters,
  readChoice,
  readPeopleFilters,
  SORT_PARAM,
  writePeopleFilters,
  type PeopleFilters,
} from './peopleView';

/**
 * The people list seen by organisation. Everything here is worked out from
 * the rows the People page already reads, so the two pages can never disagree
 * and someone hidden from one is hidden from the other.
 */

/** One organisation: its people, and where things stand with them as a whole. */
export interface OrganisationSummary {
  /** The organisation's name, or null for the people who have none on record. */
  name: string | null;
  /** Its people, most recent contact first. */
  people: PeopleOverviewRow[];
  /** The People page's headline numbers, counted over these people only. */
  counters: PeopleCounters;
  /** When the newest message with anyone there was sent. */
  lastContactAt: string | null;
}

/** The sort options on the organisations page. */
export const ORGANISATION_SORTS = ['attention', 'last-contact', 'name', 'people'] as const;
export type OrganisationSort = (typeof ORGANISATION_SORTS)[number];

/** Organisations that need the owner come first unless another order is picked. */
export const DEFAULT_ORGANISATION_SORT: OrganisationSort = 'attention';

/**
 * Everything that shapes the organisations list, kept in the URL. The filters
 * are the People page's own: an organisation is shown when at least one of
 * its people passes all of them.
 */
export interface OrganisationsView extends PeopleFilters {
  sort: OrganisationSort;
}

/** The organisation a person is listed under: a blank name counts as none. */
export function organisationNameOf(
  row: Pick<PeopleOverviewRow, 'organisation_name'>,
): string | null {
  const name = row.organisation_name?.trim() ?? '';
  return name === '' ? null : name;
}

function summarise(name: string | null, rows: readonly PeopleOverviewRow[]): OrganisationSummary {
  const people = applyPeopleView(rows, DEFAULT_VIEW);
  return {
    name,
    people,
    counters: countPeople(people),
    lastContactAt: people[0]?.last_contact_at ?? null,
  };
}

/**
 * Groups the people by the organisation they are listed under, one summary
 * each, with the people who have none in a group of their own. Organisations
 * are told apart by name, exactly as the People page shows them.
 */
export function summariseOrganisations(
  people: readonly PeopleOverviewRow[],
): OrganisationSummary[] {
  const groups = new Map<string | null, PeopleOverviewRow[]>();
  for (const row of people) {
    const name = organisationNameOf(row);
    groups.set(name, [...(groups.get(name) ?? []), row]);
  }
  return [...groups].map(([name, rows]) => summarise(name, rows));
}

/** The summary of one organisation (null: the people with none), or null when nobody is in it. */
export function findOrganisation(
  people: readonly PeopleOverviewRow[],
  name: string | null,
): OrganisationSummary | null {
  return summariseOrganisations(people).find((organisation) => organisation.name === name) ?? null;
}

/** True when the assistant has said who is waiting for at least one of these people. */
export function isAssessed(organisation: OrganisationSummary): boolean {
  return organisation.people.some((person) => person.waiting_on !== null);
}

/**
 * Reads the view out of the URL, falling back to the defaults for junk input.
 *
 * @param typeKeys The category keys the type filter may take right now.
 */
export function readOrganisationsView(
  params: URLSearchParams,
  typeKeys: readonly CategoryKey[],
): OrganisationsView {
  return {
    ...readPeopleFilters(params, typeKeys),
    sort: readChoice(params, SORT_PARAM, ORGANISATION_SORTS, DEFAULT_ORGANISATION_SORT),
  };
}

/** Writes the view back into the URL, leaving the defaults out. */
export function writeOrganisationsView(view: OrganisationsView): URLSearchParams {
  const params = writePeopleFilters(view);
  if (view.sort !== DEFAULT_ORGANISATION_SORT) params.set(SORT_PARAM, view.sort);
  return params;
}

/** The same view with every filter cleared; the chosen order is kept. */
export function clearOrganisationFilters(view: OrganisationsView): OrganisationsView {
  return { ...DEFAULT_FILTERS, sort: view.sort };
}

/** Newest contact first; an organisation nobody has written with goes last. */
function byLastContact(a: OrganisationSummary, b: OrganisationSummary): number {
  return (b.lastContactAt ?? '').localeCompare(a.lastContactAt ?? '');
}

/**
 * Most in need of the owner first: replies the owner owes that are late, then
 * every other turn that is the owner's, then nudges that are due.
 */
function byAttention(a: OrganisationSummary, b: OrganisationSummary): number {
  return (
    b.counters.overdue - a.counters.overdue ||
    b.counters.actionsForMe - a.counters.actionsForMe ||
    b.counters.timeToChase - a.counters.timeToChase
  );
}

function bySort(a: OrganisationSummary, b: OrganisationSummary, sort: OrganisationSort): number {
  switch (sort) {
    case 'attention':
      return byAttention(a, b) || byLastContact(a, b);
    case 'last-contact':
      return byLastContact(a, b);
    case 'name':
      return 0;
    case 'people':
      return b.people.length - a.people.length || byLastContact(a, b);
  }
}

/** The chosen order, then by name; the people with no organisation always come last. */
function compareOrganisations(
  a: OrganisationSummary,
  b: OrganisationSummary,
  sort: OrganisationSort,
): number {
  if (a.name === null) return 1;
  if (b.name === null) return -1;
  return bySort(a, b, sort) || a.name.localeCompare(b.name);
}

/**
 * The organisations to show, in order. Pure — the caller owns the fetching.
 *
 * The filters pick organisations, not people: one is kept when at least one
 * of its people passes every filter, and its numbers still count everyone
 * there, so they match what opening it shows.
 */
export function applyOrganisationsView(
  people: readonly PeopleOverviewRow[],
  view: OrganisationsView,
): OrganisationSummary[] {
  return summariseOrganisations(people)
    .filter((organisation) => organisation.people.some((person) => matchesFilters(person, view)))
    .sort((a, b) => compareOrganisations(a, b, view.sort));
}
