import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  addPersonNote,
  deletePersonNote,
  fetchPersonNotes,
  personNotesQueryKey,
  updatePersonNote,
} from '../api/personNotes';
import * as copy from '../copy/en';
import { NotAllowedError, NotSignedInError } from '../lib/errors';
import { useReadQuery } from './useReadQuery';

/** One change the owner can make to a person's notes. */
export type NoteAction =
  | { kind: 'add'; body: string }
  | { kind: 'update'; noteId: string; body: string }
  | { kind: 'remove'; noteId: string };

/** How the latest change ended: the sentence to show, and which change it was about. */
export interface NoteOutcome {
  action: NoteAction;
  tone: 'success' | 'error';
  text: string;
}

/** What a caller wants to hear back about one change. */
export interface RunCallbacks {
  /** Runs only if the change was saved, once the notes have been fetched again. */
  onSaved?: () => void;
}

/** What the notes section's parts need to change notes. */
export interface NotesEditor {
  /** Starts a change. */
  run: (action: NoteAction, callbacks?: RunCallbacks) => void;
  /** True while a change is on its way; every control waits for it. */
  isBusy: boolean;
  /** How the most recent change ended, or null while none has or one is waiting. */
  outcome: NoteOutcome | null;
}

/** Carries out one action and returns the sentence that says it worked. */
async function perform(personId: string, action: NoteAction): Promise<string> {
  switch (action.kind) {
    case 'add':
      await addPersonNote({ person_id: personId, body: action.body });
      return copy.notes.done.added;
    case 'update':
      await updatePersonNote(action.noteId, action.body);
      return copy.notes.done.saved;
    case 'remove':
      await deletePersonNote(action.noteId);
      return copy.notes.done.removed;
  }
}

/** Turns a failure into one sentence the owner can act on; never the database's words. */
export function noteFailureText(action: NoteAction, error: Error): string {
  if (error instanceof NotSignedInError) return copy.notes.failed.signedOut;
  if (error instanceof NotAllowedError) return copy.notes.failed.notAllowed;
  if (action.kind === 'add') return copy.notes.failed.add;
  return action.kind === 'update' ? copy.notes.failed.save : copy.notes.failed.remove;
}

/**
 * Loading and changing one person's notes.
 *
 * One change runs at a time, so two quick taps can never race each other.
 * After each change the notes are fetched again, so the list always shows
 * what the database now holds. The outcome names the change it is about, so
 * a failure can be shown next to the form or the note it concerns.
 */
export function usePersonNotes(personId: string) {
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState<NoteOutcome | null>(null);

  const notes = useReadQuery({
    queryKey: personNotesQueryKey(personId),
    queryFn: () => fetchPersonNotes(personId),
  });

  const mutation = useMutation<string, Error, NoteAction>({
    mutationFn: (action) => perform(personId, action),
    onMutate: () => {
      setOutcome(null);
    },
    onSuccess: (text, action) => {
      setOutcome({ action, tone: 'success', text });
    },
    onError: (error, action) => {
      setOutcome({ action, tone: 'error', text: noteFailureText(action, error) });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: personNotesQueryKey(personId) }),
  });

  const editor: NotesEditor = {
    run: (action, callbacks = {}) => {
      mutation.mutate(action, { onSuccess: callbacks.onSaved });
    },
    isBusy: mutation.isPending,
    outcome,
  };

  return { notes, editor };
}
