import { z } from 'zod';
import { PEOPLE_MAX_ROWS, PEOPLE_PAGE_SIZE } from '../constants/dashboard';
import { logWarning } from '../lib/logger';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { PeopleOverviewRow } from '../types/database';
import { runQuery } from './client';
import { peopleOverviewRowSchema } from './schemas';

const peopleListSchema = z.array(peopleOverviewRowSchema);

/** Query key for the one list the home page's counters and table both use. */
export const peopleQueryKey = ['people'] as const;

/** One page of the list: rows `from` up to `from + PEOPLE_PAGE_SIZE`. */
function fetchPeoplePage(from: number): Promise<PeopleOverviewRow[]> {
  const supabase = getSupabaseClient();
  return runQuery('people.list', peopleListSchema, () =>
    supabase
      .from('people_overview')
      .select('*')
      .order('last_contact_at', { ascending: false, nullsFirst: false })
      // Break ties, so rows with the same date cannot repeat or vanish between pages.
      .order('person_id', { ascending: true })
      .range(from, from + PEOPLE_PAGE_SIZE - 1),
  );
}

/**
 * Every relevant person, newest contact first.
 *
 * Read page by page, one request after the other, until a page comes back
 * short. Reading stops at `PEOPLE_MAX_ROWS` whatever happens; a list that long
 * is shown with a notice (see `peopleListIsCut`).
 *
 * Filtering and sorting happen in the browser on this single list, so the
 * counters and the table can never disagree with each other.
 */
export async function fetchPeople(): Promise<PeopleOverviewRow[]> {
  // Keyed by person, in case someone arriving mid-read moves a row onto the next page.
  const people = new Map<string, PeopleOverviewRow>();
  for (let from = 0; from < PEOPLE_MAX_ROWS; from += PEOPLE_PAGE_SIZE) {
    const page = await fetchPeoplePage(from);
    page.forEach((person) => people.set(person.person_id, person));
    if (page.length < PEOPLE_PAGE_SIZE) return [...people.values()];
  }
  logWarning('people.list_cut', { rows: people.size });
  return [...people.values()];
}
