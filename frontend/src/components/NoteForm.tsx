import { useEffect, useId, useRef, useState } from 'react';
import { MAX_NOTE_LENGTH } from '../constants/notes';
import * as copy from '../copy/en';
import { checkNoteText, NoteProblem } from '../domain/notes';
import { useFocusFirstInvalid } from '../hooks/useFocusFirstInvalid';
import { Button } from './Button';
import { fieldClassName } from './LabelledField';
import { LengthCounter } from './LengthCounter';
import { SaveFeedback } from './SaveFeedback';

interface NoteFormProps {
  /** The text to start from: empty for a new note. */
  initialBody: string;
  label: string;
  submitLabel: string;
  /** Called with the trimmed text once it passes every check. */
  onSubmit: (body: string) => void;
  onCancel: () => void;
  isBusy: boolean;
  /** Set when the last attempt from this form failed; shown so it cannot be missed. */
  errorText: string | null;
}

/** One sentence for each thing that can be wrong with a note. */
function problemText(problem: NoteProblem): string {
  return problem === NoteProblem.Empty
    ? copy.notes.problems.empty
    : copy.notes.problems.tooLong(MAX_NOTE_LENGTH);
}

/**
 * Writing or changing one note. The field takes the keyboard when the form
 * opens, since the button that opened it is gone. An empty note is turned
 * down before anything is sent, with the field marked and the sentence that
 * says why announced.
 */
export function NoteForm({
  initialBody,
  label,
  submitLabel,
  onSubmit,
  onCancel,
  isBusy,
  errorText,
}: NoteFormProps) {
  const [text, setText] = useState(initialBody);
  const [problem, setProblem] = useState<NoteProblem | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const ids = { problem: useId(), count: useId() };
  const field = useRef<HTMLTextAreaElement>(null);
  const { container, afterCheck } = useFocusFirstInvalid<HTMLFormElement>();

  useEffect(() => {
    field.current?.focus();
  }, []);

  const describedBy = [problem !== null && ids.problem, ids.count].filter(Boolean).join(' ');

  return (
    <form
      ref={container}
      noValidate
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        const checked = checkNoteText(text);
        setProblem(checked.problem);
        afterCheck();
        if (checked.body === null) return;
        setSubmitted(true);
        onSubmit(checked.body);
      }}
    >
      <div className="flex flex-col gap-1">
        <label htmlFor={`${ids.count}-field`} className="text-sm font-medium text-ink">
          {label}
        </label>
        <textarea
          ref={field}
          id={`${ids.count}-field`}
          rows={4}
          className={fieldClassName}
          value={text}
          maxLength={MAX_NOTE_LENGTH}
          disabled={isBusy}
          aria-invalid={problem !== null || undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <LengthCounter id={ids.count} length={text.length} max={MAX_NOTE_LENGTH} />
      </div>
      {problem !== null && (
        <p id={ids.problem} role="alert" className="font-medium text-danger">
          {problemText(problem)}
        </p>
      )}
      {submitted && errorText !== null && (
        <SaveFeedback outcome={{ tone: 'error', text: errorText }} />
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" disabled={isBusy}>
          {isBusy ? copy.notes.saving : submitLabel}
        </Button>
        <Button type="button" onClick={onCancel} disabled={isBusy}>
          {copy.notes.cancel}
        </Button>
      </div>
    </form>
  );
}
