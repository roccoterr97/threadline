import { useId } from 'react';
import * as copy from '../copy/en';
import {
  MAX_DESCRIPTION_LENGTH,
  MAX_LABEL_LENGTH,
  type CategoryDraft,
} from '../domain/categorySettings';
import { ColourPicker } from './ColourPicker';
import { fieldClassName, LabelledField } from './LabelledField';

const fields = copy.categorySettings.fields;

interface CategoryFieldsProps {
  draft: CategoryDraft;
  onChange: (next: CategoryDraft) => void;
  disabled: boolean;
}

/** The four things the owner says about a category: two names, who belongs, a colour. */
export function CategoryFields({ draft, onChange, disabled }: CategoryFieldsProps) {
  const hintId = useId();
  const set = <K extends keyof CategoryDraft>(key: K, value: CategoryDraft[K]) => {
    onChange({ ...draft, [key]: value });
  };

  return (
    <>
      <LabelledField label={fields.name}>
        {(id) => (
          <input
            id={id}
            type="text"
            className={fieldClassName}
            value={draft.label}
            maxLength={MAX_LABEL_LENGTH}
            disabled={disabled}
            onChange={(event) => {
              set('label', event.target.value);
            }}
          />
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
              aria-describedby={hintId}
              onChange={(event) => {
                set('group_label', event.target.value);
              }}
            />
            <p id={hintId} className="text-sm text-ink-muted">
              {fields.groupNameHint}
            </p>
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
