import { z } from 'zod';
import { TIMELINE_MESSAGE_LIMIT } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { PeopleOverviewRow } from '../types/database';
import { runQuery } from './client';
import {
  conversationWithMessagesSchema,
  peopleOverviewRowSchema,
  type ConversationWithMessages,
} from './schemas';

const personSchema = peopleOverviewRowSchema.nullable();
const conversationsSchema = z.array(conversationWithMessagesSchema);

export const personQueryKey = (personId: string) => ['person', personId] as const;
export const timelineQueryKey = (personId: string) => ['person', personId, 'timeline'] as const;

/** One person's overview row, or null when there is no such person. */
export async function fetchPerson(personId: string): Promise<PeopleOverviewRow | null> {
  const supabase = getSupabaseClient();
  return runQuery('person.get', personSchema, () =>
    supabase.from('people_overview').select('*').eq('person_id', personId).maybeSingle(),
  );
}

/** Every conversation this person has, each with its messages in date order. */
export async function fetchPersonConversations(
  personId: string,
): Promise<ConversationWithMessages[]> {
  const supabase = getSupabaseClient();
  return runQuery('person.conversations', conversationsSchema, () =>
    supabase
      .from('conversations')
      .select('*, messages(*)')
      .eq('person_id', personId)
      .order('sent_at', { referencedTable: 'messages', ascending: true })
      .limit(TIMELINE_MESSAGE_LIMIT, { referencedTable: 'messages' }),
  );
}
