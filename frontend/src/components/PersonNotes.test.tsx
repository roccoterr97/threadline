import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addPersonNote,
  deletePersonNote,
  fetchPersonNotes,
  updatePersonNote,
} from '../api/personNotes';
import { PERSON_NOTES_LIMIT } from '../constants/notes';
import * as copy from '../copy/en';
import { noteExcerpt } from '../domain/notes';
import {
  DataUnavailableError,
  NotAllowedError,
  NotSignedInError,
  TableMissingError,
} from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/renderWithProviders';
import { scrollIntoViewCalls } from '../test/scrollIntoView';
import type { PersonNoteRow } from '../types/database';
import { PersonNotes } from './PersonNotes';

vi.mock('../api/personNotes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/personNotes')>()),
  fetchPersonNotes: vi.fn(),
  addPersonNote: vi.fn(),
  updatePersonNote: vi.fn(),
  deletePersonNote: vi.fn(),
}));

const fetchNotesMock = vi.mocked(fetchPersonNotes);
const addNoteMock = vi.mocked(addPersonNote);
const updateNoteMock = vi.mocked(updatePersonNote);
const deleteNoteMock = vi.mocked(deletePersonNote);

const PERSON_ID = 'p-01';

function note(id: string, body: string, createdAt: string, updatedAt = createdAt): PersonNoteRow {
  return { id, person_id: PERSON_ID, body, created_at: createdAt, updated_at: updatedAt };
}

const FAIR = note('n-1', 'Met at the Lyon fair.\nPrefers calls after 4pm.', '2026-03-12T08:30:00Z');
const BROCHURE = note(
  'n-2',
  'Asked for the brochure in French.',
  '2026-03-14T10:00:00Z',
  '2026-03-16T09:00:00Z',
);

function renderNotes() {
  return renderWithProviders(<PersonNotes personId={PERSON_ID} />);
}

function section() {
  return within(screen.getByRole('region', { name: copy.notes.title }));
}

beforeEach(() => {
  fetchNotesMock.mockResolvedValue([BROCHURE, FAIR]);
  addNoteMock.mockResolvedValue(undefined);
  updateNoteMock.mockResolvedValue(undefined);
  deleteNoteMock.mockResolvedValue(undefined);
});

describe('PersonNotes — reading', () => {
  it('lists the notes as fetched, newest first, each with its dates', async () => {
    renderNotes();
    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Asked for the brochure in French.');
    expect(items[0]).toHaveTextContent(/Written 14 Mar 2026 · changed 16 Mar 2026/);
    expect(items[1]).toHaveTextContent(/Written 12 Mar 2026/);
    expect(items[1]).not.toHaveTextContent(/changed/);
  });

  it('says so when there are no notes yet, and still offers to add one', async () => {
    fetchNotesMock.mockResolvedValue([]);
    renderNotes();
    expect(await screen.findByText(copy.notes.empty)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.notes.add })).toBeInTheDocument();
  });

  it('explains plainly when the database does not have the notes table yet', async () => {
    fetchNotesMock.mockRejectedValue(new TableMissingError('notes.list'));
    renderNotes();
    expect(await screen.findByText(copy.notes.notSetUp)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: copy.notes.add })).not.toBeInTheDocument();
  });

  it('offers a retry when the notes cannot be loaded for another reason', async () => {
    fetchNotesMock.mockRejectedValueOnce(new DataUnavailableError('notes.list'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.states.retry }));
    expect(await screen.findByText('Asked for the brochure in French.')).toBeInTheDocument();
  });

  it('says when only the newest notes are shown', async () => {
    const many = Array.from({ length: PERSON_NOTES_LIMIT }, (_, index) =>
      note(`n-${index}`, `Note ${index}`, '2026-03-12T08:30:00Z'),
    );
    fetchNotesMock.mockResolvedValue(many);
    renderNotes();
    expect(
      await screen.findByText(copy.notes.onlyNewestShown(PERSON_NOTES_LIMIT)),
    ).toBeInTheDocument();
  });
});

describe('PersonNotes — adding', () => {
  it('saves the typed note, trimmed, and says so with the keyboard on the message', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    const field = screen.getByRole('textbox', { name: copy.notes.fieldLabel });
    expect(field).toHaveFocus();
    fetchNotesMock.mockResolvedValue([note('n-3', 'Sent the quote.', '2026-03-20T08:00:00Z')]);

    await user.type(field, '  Sent the quote.  ');
    await user.click(screen.getByRole('button', { name: copy.notes.save }));

    expect(addNoteMock).toHaveBeenCalledWith({ person_id: PERSON_ID, body: 'Sent the quote.' });
    const status = await screen.findByRole('status', { name: '' });
    expect(status).toHaveTextContent(copy.notes.done.added);
    expect(status).toHaveFocus();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(await screen.findByText('Sent the quote.')).toBeInTheDocument();
  });

  it('refuses an empty note before sending anything, and points at the field', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    const field = screen.getByRole('textbox', { name: copy.notes.fieldLabel });
    await user.type(field, '   ');

    await user.click(screen.getByRole('button', { name: copy.notes.save }));

    expect(addNoteMock).not.toHaveBeenCalled();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(copy.notes.problems.empty);
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription(expect.stringContaining(copy.notes.problems.empty));
    expect(field).toHaveFocus();
  });

  it('keeps the text and gives the keyboard to the message when the save fails', async () => {
    addNoteMock.mockRejectedValue(new DataUnavailableError('notes.add'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    await user.type(screen.getByRole('textbox', { name: copy.notes.fieldLabel }), 'Sent the quote.');

    await user.click(screen.getByRole('button', { name: copy.notes.save }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(copy.notes.failed.add);
    expect(alert).toHaveFocus();
    expect(scrollIntoViewCalls(alert)).toHaveLength(1);
    expect(screen.getByRole('textbox', { name: copy.notes.fieldLabel })).toHaveValue(
      'Sent the quote.',
    );
  });

  it('says so plainly when the save was refused because the sign-in ran out', async () => {
    addNoteMock.mockRejectedValue(new NotSignedInError('notes.add'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    await user.type(screen.getByRole('textbox', { name: copy.notes.fieldLabel }), 'Hello');
    await user.click(screen.getByRole('button', { name: copy.notes.save }));
    expect(await screen.findByRole('alert')).toHaveTextContent(copy.notes.failed.signedOut);
  });

  it('says the account is not allowed, rather than signed out, when the save was forbidden', async () => {
    addNoteMock.mockRejectedValue(new NotAllowedError('notes.add'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    await user.type(screen.getByRole('textbox', { name: copy.notes.fieldLabel }), 'Hello');
    await user.click(screen.getByRole('button', { name: copy.notes.save }));
    expect(await screen.findByRole('alert')).toHaveTextContent(copy.notes.failed.notAllowed);
  });

  it('puts the keyboard back on "Add a note" when the form is closed without saving', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: copy.notes.add }));
    await user.click(screen.getByRole('button', { name: copy.notes.cancel }));
    expect(screen.getByRole('button', { name: copy.notes.add })).toHaveFocus();
  });
});

describe('PersonNotes — changing', () => {
  const changeFair = copy.notes.changeLabel(noteExcerpt(FAIR.body));

  it('names each note in its buttons by its opening words', async () => {
    renderNotes();
    expect(changeFair).toBe('Change the note “Met at the Lyon fair. Prefers calls…”');
    expect(await screen.findByRole('button', { name: changeFair })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: copy.notes.removeLabel('Asked for the brochure in French.') }),
    ).toBeInTheDocument();
  });

  it('saves the new text and shows it, with the keyboard on the message', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: changeFair }));
    const field = screen.getByRole('textbox', { name: copy.notes.editFieldLabel });
    expect(field).toHaveFocus();
    expect(field).toHaveValue(FAIR.body);
    fetchNotesMock.mockResolvedValue([BROCHURE, { ...FAIR, body: 'Met in Lyon.' }]);

    await user.clear(field);
    await user.type(field, 'Met in Lyon.');
    await user.click(screen.getByRole('button', { name: copy.notes.saveChanges }));

    expect(updateNoteMock).toHaveBeenCalledWith('n-1', 'Met in Lyon.');
    const status = await screen.findByRole('status', { name: '' });
    expect(status).toHaveTextContent(copy.notes.done.saved);
    expect(status).toHaveFocus();
    expect(await screen.findByText('Met in Lyon.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows a failed change next to the form, with the keyboard on the message', async () => {
    updateNoteMock.mockRejectedValue(new DataUnavailableError('notes.update'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: changeFair }));
    await user.click(screen.getByRole('button', { name: copy.notes.saveChanges }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(copy.notes.failed.save);
    expect(alert).toHaveFocus();
    expect(screen.getByRole('textbox', { name: copy.notes.editFieldLabel })).toBeInTheDocument();
  });

  it('puts the keyboard back on "Change" when the change is given up', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: changeFair }));
    await user.click(screen.getByRole('button', { name: copy.notes.cancel }));
    expect(screen.getByRole('button', { name: changeFair })).toHaveFocus();
  });
});

describe('PersonNotes — deleting', () => {
  const removeBrochure = copy.notes.removeLabel('Asked for the brochure in French.');

  it('asks first, then deletes and says so', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: removeBrochure }));
    const panel = screen.getByRole('group', { name: copy.notes.removeConfirmTitle });
    expect(panel).toHaveFocus();
    expect(panel).toHaveTextContent('“Asked for the brochure in French.” will be gone for good.');
    expect(deleteNoteMock).not.toHaveBeenCalled();
    fetchNotesMock.mockResolvedValue([FAIR]);

    await user.click(screen.getByRole('button', { name: copy.notes.removeConfirm }));

    expect(deleteNoteMock).toHaveBeenCalledWith('n-2');
    const status = await screen.findByRole('status', { name: '' });
    expect(status).toHaveTextContent(copy.notes.done.removed);
    expect(status).toHaveFocus();
    await waitFor(() => {
      expect(screen.queryByText('Asked for the brochure in French.')).not.toBeInTheDocument();
    });
  });

  it('keeps the note and gives the keyboard to the message when deleting fails', async () => {
    deleteNoteMock.mockRejectedValue(new DataUnavailableError('notes.delete'));
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: removeBrochure }));
    await user.click(screen.getByRole('button', { name: copy.notes.removeConfirm }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(copy.notes.failed.remove);
    expect(alert).toHaveFocus();
    expect(scrollIntoViewCalls(alert)).toHaveLength(1);
    expect(screen.getByText('Asked for the brochure in French.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.notes.removeConfirm })).toBeInTheDocument();
  });

  it('puts the keyboard back on "Delete" when the owner keeps the note', async () => {
    const { user } = renderNotes();
    await user.click(await screen.findByRole('button', { name: removeBrochure }));
    await user.click(screen.getByRole('button', { name: copy.notes.removeCancel }));
    expect(screen.getByRole('button', { name: removeBrochure })).toHaveFocus();
    expect(screen.getByText('Asked for the brochure in French.')).toBeInTheDocument();
  });
});

describe('PersonNotes — accessibility', () => {
  it('has no axe violations while reading, writing and confirming', async () => {
    const { container, user } = renderNotes();
    await screen.findByText('Asked for the brochure in French.');
    await expectNoAxeViolations(container);

    await user.click(screen.getByRole('button', { name: copy.notes.add }));
    await user.click(
      screen.getByRole('button', {
        name: copy.notes.removeLabel('Asked for the brochure in French.'),
      }),
    );
    expect(section().getByRole('textbox')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });
});
