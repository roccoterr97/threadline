import { z } from 'zod';
import { COMING_UP_DAYS, COMING_UP_LIMIT } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { UpcomingMeetingRow } from '../types/database';
import { runQuery } from './client';
import { upcomingMeetingRowSchema } from './schemas';

const meetingsSchema = z.array(upcomingMeetingRowSchema);

const DAY_MS = 86_400_000;

/** Only the columns the strip shows, with the person and organisation embedded. */
const MEETING_COLUMNS =
  'id, subject, meeting_at, person_id, people(full_name, organisations(name))';

export const upcomingMeetingsQueryKey = ['meetings', 'upcoming'] as const;

/**
 * Calendar meetings from `now` to the same moment `COMING_UP_DAYS` later,
 * soonest first. Cancelled meetings have no `meeting_at`, so they never match;
 * conversations judged to be noise are left out.
 */
export async function fetchUpcomingMeetings(now: Date): Promise<UpcomingMeetingRow[]> {
  const supabase = getSupabaseClient();
  const from = now.toISOString();
  const until = new Date(now.getTime() + COMING_UP_DAYS * DAY_MS).toISOString();
  return runQuery('meetings.upcoming', meetingsSchema, () =>
    supabase
      .from('conversations')
      .select(MEETING_COLUMNS)
      .eq('channel', 'calendar')
      .neq('relevance', 'noise')
      .gte('meeting_at', from)
      .lt('meeting_at', until)
      .order('meeting_at', { ascending: true })
      .limit(COMING_UP_LIMIT),
  );
}
