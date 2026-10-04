/** Operational tuning for the owner's hand-typed notes on a person. */

/**
 * How long one note can be. A note, not a document; the database holds the
 * same limit (migration 0016), and a test keeps the two equal.
 */
export const MAX_NOTE_LENGTH = 2000;

/** Upper bound on the notes fetched for one person, newest first. */
export const PERSON_NOTES_LIMIT = 200;

/** How much of a note names it in a button or a question: "Change the note “Met at…”". */
export const NOTE_EXCERPT_LENGTH = 40;
