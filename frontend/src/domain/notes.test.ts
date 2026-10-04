import { describe, expect, it } from 'vitest';
import { MAX_NOTE_LENGTH, NOTE_EXCERPT_LENGTH } from '../constants/notes';
import { checkNoteText, NoteProblem, noteExcerpt, wasEdited } from './notes';

describe('checkNoteText', () => {
  it('keeps a note as typed, without the spaces around it', () => {
    expect(checkNoteText('  Met at the Lyon fair.\n')).toEqual({
      body: 'Met at the Lyon fair.',
      problem: null,
    });
  });

  it('refuses an empty note, and one made of spaces or line breaks', () => {
    for (const text of ['', '   ', '\n\n', ' \t\n ']) {
      expect(checkNoteText(text)).toEqual({ body: null, problem: NoteProblem.Empty });
    }
  });

  it('refuses a note over the limit, counted after trimming', () => {
    const longest = 'a'.repeat(MAX_NOTE_LENGTH);
    expect(checkNoteText(`  ${longest}  `).body).toBe(longest);
    expect(checkNoteText(`${longest}a`)).toEqual({ body: null, problem: NoteProblem.TooLong });
  });
});

describe('wasEdited', () => {
  it('is true only once the text changed after the note was written', () => {
    const written = '2026-09-12T08:30:00+00:00';
    expect(wasEdited({ created_at: written, updated_at: written })).toBe(false);
    expect(wasEdited({ created_at: written, updated_at: '2026-09-14T10:00:00+00:00' })).toBe(true);
  });
});

describe('noteExcerpt', () => {
  it('gives a short note whole, on one line', () => {
    expect(noteExcerpt('Met at the\nLyon fair.')).toBe('Met at the Lyon fair.');
  });

  it('cuts a long note at a word and marks the cut', () => {
    const excerpt = noteExcerpt('Met at the Lyon fair and talked for an hour about routes.');
    expect(excerpt).toBe('Met at the Lyon fair and talked for an…');
    expect(excerpt.length).toBeLessThanOrEqual(NOTE_EXCERPT_LENGTH + 1);
  });

  it('cuts inside a word when the note has no space to cut at', () => {
    expect(noteExcerpt('x'.repeat(100))).toBe(`${'x'.repeat(NOTE_EXCERPT_LENGTH)}…`);
  });
});
