import { z } from 'zod';
import { PERSON_NOTES_LIMIT } from '../constants/notes';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { PersonNoteInsert, PersonNoteRow } from '../types/database';
import { runMutation, runQuery } from './client';
import { personNoteRowSchema } from './schemas';

/**
 * The notes the owner types on a person's page. Theirs alone: nothing here is
 * read by the assistant or put in the morning e-mail.
 */

const TABLE = 'person_notes';
const notesSchema = z.array(personNoteRowSchema);

export const personNotesQueryKey = (personId: string) => ['person', personId, 'notes'] as const;

/**
 * One person's notes, newest first.
 *
 * @throws {TableMissingError} when the database does not have the notes table
 *   yet, so the page can say which structure file to apply.
 */
export async function fetchPersonNotes(personId: string): Promise<PersonNoteRow[]> {
  const supabase = getSupabaseClient();
  return runQuery('notes.list', notesSchema, () =>
    supabase
      .from(TABLE)
      .select('*')
      .eq('person_id', personId)
      .order('created_at', { ascending: false })
      .limit(PERSON_NOTES_LIMIT),
  );
}

/** Adds a note. The text has already passed `checkNoteText`. */
export async function addPersonNote(note: PersonNoteInsert): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('notes.add', () => supabase.from(TABLE).insert(note));
}

/** Replaces the text of one note. Its person and its dates stay as they are. */
export async function updatePersonNote(noteId: string, body: string): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('notes.update', () => supabase.from(TABLE).update({ body }).eq('id', noteId));
}

/** Removes one note for good. */
export async function deletePersonNote(noteId: string): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('notes.delete', () => supabase.from(TABLE).delete().eq('id', noteId));
}
