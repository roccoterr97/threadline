import type { CategoryKey, ContactStatus, PeopleOverviewRow, WaitingOn } from '../types/database';

/**
 * Everything the owner may set by hand on a person.
 *
 * A null field means "no correction here" — the assistant's own answer keeps
 * applying to it.
 */
export interface OverrideValues {
  status: ContactStatus | null;
  waiting_on: WaitingOn | null;
  next_action: string | null;
  due_date: string | null;
  person_type: CategoryKey | null;
  note: string | null;
}

/** True when at least one field carries a correction. */
export function hasAnyOverride(values: OverrideValues): boolean {
  return Object.values(values).some((value) => value !== null);
}

/**
 * Works out what the person row will look like once a correction is saved, so
 * the screen can show the new values before the database has confirmed them.
 *
 * Mirrors the `people_overview` rule: an override wins, otherwise the AI value
 * stands. `note` is not part of the view, so it is not applied here.
 */
export function applyOverrideToPerson(
  person: PeopleOverviewRow,
  values: OverrideValues,
): PeopleOverviewRow {
  return {
    ...person,
    status: values.status ?? person.status,
    waiting_on: values.waiting_on ?? person.waiting_on,
    next_action: values.next_action ?? person.next_action,
    due_date: values.due_date ?? person.due_date,
    person_type: values.person_type ?? person.person_type,
    has_override: hasAnyOverride(values),
  };
}
