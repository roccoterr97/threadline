import { useId } from 'react';
import * as copy from '../copy/en';
import {
  MAX_DESCRIPTION_LENGTH,
  MAX_LABEL_LENGTH,
  problemField,
  type CategoryDraft,
  type DraftProblem,
} from '../domain/categorySettings';
import { ColourPicker } from './ColourPicker';
import { fieldClassName, LabelledField } from './LabelledField';
import { LengthCounter } from './LengthCounter';

const fields = copy.categorySettings.fields;

interface CategoryFieldsProps {
  draft: CategoryDraft;
  onChange: (next: CategoryDraft) => void;
  disabled: boolean;
  /** What is wrong with the draft; its field is marked invalid and points at the message. */
  problem: DraftProblem | null;
  /** The id of the element that says what is wrong. */
  problemId: string;
}

/** The ids a field is described by, leaving out the ones that are not there. */
function describedBy(...ids: Array<string | false>): string {
  return ids.filter(Boolean).join(' ');
}

/** The four things the owner says about a category: two names, who belongs, a colour. */
export function CategoryFields({
  draft,
  onChange,
  disabled,
  problem,
  problemId,
}: CategoryFieldsProps) {
  const ids = { name: useId(), group: useId(), hint: useId() };
  const invalid = problemField(problem);
  const set = <K extends keyof CategoryDraft>(key: K, value: CategoryDraft[K]) => {
    onChange({ ...draft, [key]: value });
  };
  const errorFor = (field: keyof CategoryDraft) => invalid === field && problemId;

  return (
    <>
      <LabelledField label={fields.name}>
        {(id) => (
          <>
            <input
              id={id}
              type="text"
              className={fieldClassName}
              value={draft.label}
              maxLength={MAX_LABEL_LENGTH}
              disabled={disabled}
              aria-invalid={invalid === 'label' || undefined}
              aria-describedby={describedBy(errorFor('label'), ids.name)}
              onChange={(event) => {
                set('label', event.target.value);
              }}
            />
            <LengthCounter id={ids.name} length={draft.label.length} max={MAX_LABEL_LENGTH} />
          </>
        )}
      </LabelledField>
      <LabelledField label={fields.groupName}>
        {(id) => (
          <>
            <input
              id={id}
              type="text"
              className={fieldClassName}
              value={draft.group_label}
              maxLength={MAX_LABEL_LENGTH}
              disabled={disabled}
              aria-invalid={invalid === 'group_label' || undefined}
              aria-describedby={describedBy(errorFor('group_label'), ids.hint, ids.group)}
              onChange={(event) => {
                set('group_label', event.target.value);
              }}
            />
            <p id={ids.hint} className="text-sm text-ink-muted">
              {fields.groupNameHint}
            </p>
            <LengthCounter
              id={ids.group}
              length={draft.group_label.length}
              max={MAX_LABEL_LENGTH}
            />
          </>
        )}
      </LabelledField>
      <LabelledField label={fields.description}>
        {(id) => (
          <textarea
            id={id}
            rows={3}
            className={fieldClassName}
            value={draft.description}
            maxLength={MAX_DESCRIPTION_LENGTH}
            disabled={disabled}
            aria-invalid={invalid === 'description' || undefined}
            aria-describedby={describedBy(errorFor('description')) || undefined}
            onChange={(event) => {
              set('description', event.target.value);
            }}
          />
        )}
      </LabelledField>
      <ColourPicker
        value={draft.colour}
        disabled={disabled}
        onChange={(colour) => {
          set('colour', colour);
        }}
      />
    </>
  );
}
