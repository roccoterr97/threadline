import { z } from 'zod';
import { PEOPLE_PAGE_SIZE } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { PeopleOverviewRow } from '../types/database';
import { runQuery } from './client';
import { peopleOverviewRowSchema } from './schemas';

const peopleListSchema = z.array(peopleOverviewRowSchema);

/** Query key for the one list the home page's counters and table both use. */
export const peopleQueryKey = ['people'] as const;

/**
 * Every relevant person, newest contact first.
 *
 * Filtering and sorting happen in the browser on this single list, so the
 * counters and the table can never disagree with each other.
 */
export async function fetchPeople(): Promise<PeopleOverviewRow[]> {
  const supabase = getSupabaseClient();
  return runQuery('people.list', peopleListSchema, () =>
    supabase
      .from('people_overview')
      .select('*')
      .order('last_contact_at', { ascending: false, nullsFirst: false })
      .limit(PEOPLE_PAGE_SIZE),
  );
}
