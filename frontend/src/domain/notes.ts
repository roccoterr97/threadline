import { MAX_NOTE_LENGTH, NOTE_EXCERPT_LENGTH } from '../constants/notes';
import type { PersonNoteRow } from '../types/database';

/** The rules a hand-typed note follows, with nothing about the screen in them. */

/** What can be wrong with a note before it is saved. */
export enum NoteProblem {
  Empty = 'empty',
  TooLong = 'too_long',
}

/** A note ready to save (trimmed), or the one thing wrong with it. */
export type NoteCheck = { body: string; problem: null } | { body: null; problem: NoteProblem };

/**
 * Checks a typed note. Surrounding blank lines and spaces are dropped, so a
 * note of nothing but spaces or line breaks is refused rather than saved.
 */
export function checkNoteText(text: string): NoteCheck {
  const body = text.trim();
  if (body === '') return { body: null, problem: NoteProblem.Empty };
  if (body.length > MAX_NOTE_LENGTH) return { body: null, problem: NoteProblem.TooLong };
  return { body, problem: null };
}

/** True when the text of a note was changed after it was written. */
export function wasEdited(note: Pick<PersonNoteRow, 'created_at' | 'updated_at'>): boolean {
  return note.updated_at !== note.created_at;
}

/**
 * The opening of a note, on one line, to name it in a button or a question.
 * Long notes are cut at a word where one is near, with an ellipsis.
 */
export function noteExcerpt(body: string): string {
  const oneLine = body.replace(/\s+/g, ' ').trim();
  if (oneLine.length <= NOTE_EXCERPT_LENGTH) return oneLine;
  const cut = oneLine.slice(0, NOTE_EXCERPT_LENGTH);
  const lastSpace = cut.lastIndexOf(' ');
  const kept = lastSpace > NOTE_EXCERPT_LENGTH / 2 ? cut.slice(0, lastSpace) : cut;
  return `${kept.trimEnd()}…`;
}
