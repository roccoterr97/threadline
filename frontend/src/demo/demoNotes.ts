import { z } from 'zod';
import { personNoteRowSchema } from '../api/schemas';
import { MAX_NOTE_LENGTH } from '../constants/notes';
import type { PersonNoteRow } from '../types/database';
import { hoursBefore } from './demoCalendar';

/**
 * The demo's notes: two invented ones on the first person, and the rules the
 * real table keeps (a note names a person who exists, is never blank and has
 * a length limit). Rows are plain objects, as every demo table's are.
 */

/** Chooses the rows a filter applies to. */
type RowFilter = (row: object) => boolean;

/** What the demo answers when a write breaks a rule the real database keeps. */
export interface NoteWriteRefusal {
  reason: 'no_such_person' | 'breaks_rule';
}

/** The same rule as the database's check on `person_notes.body`. */
const noteBody = z.string().regex(/\S/).max(MAX_NOTE_LENGTH);
const noteInsertSchema = personNoteRowSchema
  .pick({ person_id: true })
  .extend({ body: noteBody })
  .strict();
const noteChangesSchema = z.object({ body: noteBody }).strict();

/** The invented owner's notes on Maya Lindqvist, written over the last few days. */
export function buildDemoNotes(now: Date): PersonNoteRow[] {
  const earlier = hoursBefore(now, 9 * 24 + 2);
  const later = hoursBefore(now, 6 * 24 + 5);
  return [
    {
      id: 'demo-n01',
      created_at: earlier,
      updated_at: earlier,
      person_id: 'demo-p01',
      body: 'Met at the Rotterdam logistics fair. Prefers a call after 4pm; mornings are for the depot.',
    },
    {
      id: 'demo-n02',
      created_at: later,
      updated_at: hoursBefore(now, 2 * 24 + 1),
      person_id: 'demo-p01',
      body: 'Her team is twelve planners. The depot manager, Joris Vermeulen, decides with her.',
    },
  ];
}

/** Checks a new note, as the database would; `people` says who exists. */
export function checkNoteInsert(
  values: unknown,
  people: ReadonlySet<string>,
): { note: Pick<PersonNoteRow, 'person_id' | 'body'> } | NoteWriteRefusal {
  const parsed = noteInsertSchema.safeParse(values);
  if (!parsed.success) return { reason: 'breaks_rule' };
  if (!people.has(parsed.data.person_id)) return { reason: 'no_such_person' };
  return { note: parsed.data };
}

/** Checks a change to a note's text, as the database would. */
export function checkNoteChanges(changes: unknown): { body: string } | NoteWriteRefusal {
  const parsed = noteChangesSchema.safeParse(changes);
  return parsed.success ? parsed.data : { reason: 'breaks_rule' };
}

/** A new row with its id and both dates set to `stamp`. */
export function newNoteRow(
  id: string,
  note: Pick<PersonNoteRow, 'person_id' | 'body'>,
  stamp: string,
): PersonNoteRow {
  return { id, created_at: stamp, updated_at: stamp, ...note };
}

/** Changes the text of the notes `match` picks, dating the change `stamp`. */
export function changeNotes(
  rows: readonly PersonNoteRow[],
  match: RowFilter,
  body: string,
  stamp: string,
): PersonNoteRow[] {
  return rows.map((row) => (match(row) ? { ...row, body, updated_at: stamp } : row));
}
