import { useEffect, useRef, useState } from 'react';
import * as copy from '../copy/en';
import { noteExcerpt, wasEdited } from '../domain/notes';
import type { NoteAction, NotesEditor } from '../hooks/usePersonNotes';
import { formatDate } from '../lib/format';
import type { PersonNoteRow } from '../types/database';
import { Button } from './Button';
import { ConfirmPanel } from './ConfirmPanel';
import { NoteForm } from './NoteForm';

interface NoteRowProps {
  note: PersonNoteRow;
  editor: NotesEditor;
}

type Mode = 'view' | 'editing' | 'confirming-removal';

/** The failure message meant for this row's change of `kind`, if the last change was that. */
function failureFor(editor: NotesEditor, kind: NoteAction['kind'], noteId: string): string | null {
  const outcome = editor.outcome;
  if (outcome === null || outcome.tone !== 'error') return null;
  const { action } = outcome;
  if (action.kind === 'add' || action.kind !== kind || action.noteId !== noteId) return null;
  return outcome.text;
}

/**
 * One note: its text and dates, with buttons to change or delete it. Deleting
 * asks first, since it cannot be undone. Backing out of either puts the
 * keyboard back on the button that started it.
 */
export function NoteRow({ note, editor }: NoteRowProps) {
  const [mode, setMode] = useState<Mode>('view');
  const [attempted, setAttempted] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);
  const removeButton = useRef<HTMLButtonElement>(null);
  const refocus = useRef<'change' | 'remove' | null>(null);
  const excerpt = noteExcerpt(note.body);

  useEffect(() => {
    if (mode !== 'view' || refocus.current === null) return;
    (refocus.current === 'change' ? changeButton : removeButton).current?.focus();
    refocus.current = null;
  }, [mode]);

  const backToView = (button: 'change' | 'remove') => {
    refocus.current = button;
    setMode('view');
  };

  return (
    <li className="flex flex-col gap-3 rounded-token-lg border border-line bg-surface p-4">
      <p className="text-sm text-ink-muted">
        <time dateTime={note.created_at}>{copy.notes.writtenOn(formatDate(note.created_at))}</time>
        {wasEdited(note) && (
          <>
            {' · '}
            <time dateTime={note.updated_at}>{copy.notes.changedOn(formatDate(note.updated_at))}</time>
          </>
        )}
      </p>

      {mode !== 'editing' && <p className="whitespace-pre-line break-words text-ink">{note.body}</p>}

      {mode === 'editing' && (
        <NoteForm
          initialBody={note.body}
          label={copy.notes.editFieldLabel}
          submitLabel={copy.notes.saveChanges}
          isBusy={editor.isBusy}
          errorText={failureFor(editor, 'update', note.id)}
          onCancel={() => {
            backToView('change');
          }}
          onSubmit={(body) => {
            editor.run(
              { kind: 'update', noteId: note.id, body },
              {
                onSaved: () => {
                  setMode('view');
                },
              },
            );
          }}
        />
      )}

      {mode === 'confirming-removal' && (
        <ConfirmPanel
          title={copy.notes.removeConfirmTitle}
          body={copy.notes.removeConfirmBody(excerpt)}
          confirmLabel={copy.notes.removeConfirm}
          cancelLabel={copy.notes.removeCancel}
          isBusy={editor.isBusy}
          errorText={attempted ? failureFor(editor, 'remove', note.id) : null}
          onConfirm={() => {
            setAttempted(true);
            editor.run({ kind: 'remove', noteId: note.id });
          }}
          onCancel={() => {
            backToView('remove');
          }}
        />
      )}

      {mode === 'view' && (
        <div className="flex flex-wrap gap-2">
          <Button
            ref={changeButton}
            aria-label={copy.notes.changeLabel(excerpt)}
            disabled={editor.isBusy}
            onClick={() => {
              setMode('editing');
            }}
          >
            {copy.notes.change}
          </Button>
          <Button
            ref={removeButton}
            variant="danger"
            aria-label={copy.notes.removeLabel(excerpt)}
            disabled={editor.isBusy}
            onClick={() => {
              setAttempted(false);
              setMode('confirming-removal');
            }}
          >
            {copy.notes.remove}
          </Button>
        </div>
      )}
    </li>
  );
}
