import { useEffect, useRef, useState } from 'react';
import { PERSON_NOTES_LIMIT } from '../constants/notes';
import * as copy from '../copy/en';
import { usePersonNotes, type NotesEditor } from '../hooks/usePersonNotes';
import { TableMissingError } from '../lib/errors';
import { Button } from './Button';
import { ErrorState } from './ErrorState';
import { LoadingState } from './LoadingState';
import { NoteForm } from './NoteForm';
import { NoteRow } from './NoteRow';
import { RefreshFailedNote } from './RefreshFailedNote';
import { SaveFeedback } from './SaveFeedback';

interface PersonNotesProps {
  personId: string;
}

/** The failure message meant for the add form, if the last change was an add that failed. */
function addFailure(editor: NotesEditor): string | null {
  const outcome = editor.outcome;
  if (outcome === null || outcome.tone !== 'error' || outcome.action.kind !== 'add') return null;
  return outcome.text;
}

/**
 * The notes the owner typed on this person, newest first, with a way to add
 * one. A change that worked is said once, under the heading, and takes the
 * keyboard; a change that failed says so next to the form or the note it was
 * about. A database without the notes table yet explains itself instead of
 * breaking the page.
 */
export function PersonNotes({ personId }: PersonNotesProps) {
  const { notes, editor } = usePersonNotes(personId);
  const [adding, setAdding] = useState(false);
  const addButton = useRef<HTMLButtonElement>(null);
  const refocusAdd = useRef(false);

  useEffect(() => {
    if (adding || !refocusAdd.current) return;
    refocusAdd.current = false;
    addButton.current?.focus();
  }, [adding]);

  const success = editor.outcome?.tone === 'success' ? editor.outcome : null;
  const notSetUp = notes.isError && notes.error instanceof TableMissingError;

  return (
    <section
      aria-labelledby={`notes-${personId}`}
      className="flex flex-col gap-3 rounded-token-lg border border-line bg-surface p-4 shadow-card"
    >
      <div>
        <h2 id={`notes-${personId}`} className="text-base font-semibold text-ink">
          {copy.notes.title}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">{copy.notes.intro}</p>
      </div>

      {success !== null && <SaveFeedback outcome={{ tone: 'success', text: success.text }} />}

      <RefreshFailedNote show={notes.refreshFailed} />

      {notes.isPending && <LoadingState label={copy.states.loading} />}

      {notSetUp && <p className="text-ink-muted">{copy.notes.notSetUp}</p>}

      {notes.isError && !notSetUp && (
        <ErrorState
          error={notes.error}
          onRetry={() => {
            void notes.refetch();
          }}
        />
      )}

      {notes.isSuccess && (
        <>
          {adding ? (
            <NoteForm
              initialBody=""
              label={copy.notes.fieldLabel}
              submitLabel={copy.notes.save}
              isBusy={editor.isBusy}
              errorText={addFailure(editor)}
              onCancel={() => {
                refocusAdd.current = true;
                setAdding(false);
              }}
              onSubmit={(body) => {
                editor.run(
                  { kind: 'add', body },
                  {
                    onSaved: () => {
                      setAdding(false);
                    },
                  },
                );
              }}
            />
          ) : (
            <div>
              <Button
                ref={addButton}
                variant="primary"
                disabled={editor.isBusy}
                onClick={() => {
                  setAdding(true);
                }}
              >
                {copy.notes.add}
              </Button>
            </div>
          )}

          {notes.data.length === 0 && <p className="text-ink-muted">{copy.notes.empty}</p>}
          {notes.data.length > 0 && (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {notes.data.map((note) => (
                <NoteRow key={note.id} note={note} editor={editor} />
              ))}
            </ul>
          )}
          {notes.data.length >= PERSON_NOTES_LIMIT && (
            <p className="text-sm text-ink-muted">
              {copy.notes.onlyNewestShown(PERSON_NOTES_LIMIT)}
            </p>
          )}
        </>
      )}
    </section>
  );
}
