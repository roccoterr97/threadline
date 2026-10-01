import { getSupabaseClient } from '../lib/supabaseClient';
import type { PersonOverrideRow, PersonOverrideWrite } from '../types/database';
import { runMutation, runQuery } from './client';
import { personOverrideRowSchema } from './schemas';

const overrideSchema = personOverrideRowSchema.nullable();

export const overrideQueryKey = (personId: string) => ['person', personId, 'override'] as const;

/** The owner's hand-made correction for this person, or null if there is none. */
export async function fetchOverride(personId: string): Promise<PersonOverrideRow | null> {
  const supabase = getSupabaseClient();
  return runQuery('override.get', overrideSchema, () =>
    supabase.from('person_overrides').select('*').eq('person_id', personId).maybeSingle(),
  );
}

/** Creates or replaces the correction for one person. */
export async function saveOverride(values: PersonOverrideWrite): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('override.save', () =>
    supabase.from('person_overrides').upsert(values, { onConflict: 'person_id' }),
  );
}

/** Removes the correction, so the assistant's own view applies again. */
export async function clearOverride(personId: string): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('override.clear', () =>
    supabase.from('person_overrides').delete().eq('person_id', personId),
  );
}

/**
 * Takes a person off the list: their relevance becomes "noise", so no later
 * run looks at their messages again (until `markPersonAsRelevant` undoes it).
 */
export async function markPersonAsNoise(personId: string): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('person.mark_noise', () =>
    supabase.from('people').update({ relevance: 'noise' }).eq('id', personId),
  );
}

/**
 * Puts a hidden person back on the list. Only people on the list can be
 * hidden from the dashboard, so "relevant" is always what they were before.
 */
export async function markPersonAsRelevant(personId: string): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('person.mark_relevant', () =>
    supabase.from('people').update({ relevance: 'relevant' }).eq('id', personId),
  );
}
