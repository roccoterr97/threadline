import { useState } from 'react';
import { contactStatusSchema, waitingOnSchema } from '../api/schemas';
import * as copy from '../copy/en';
import { hasAnyOverride, type OverrideValues } from '../domain/overrides';
import type { Vocabulary } from '../domain/vocabulary';
import type { PersonOverrideRow } from '../types/database';
import { Button } from './Button';
import { CategorySelect } from './CategorySelect';
import { fieldClassName, LabelledField } from './LabelledField';
import { OverrideSelect } from './OverrideSelect';

interface OverrideFormProps {
  override: PersonOverrideRow | null;
  vocabulary: Vocabulary;
  onSave: (values: OverrideValues) => void;
  onClear: () => void;
  isSaving: boolean;
  isClearing: boolean;
}

/** Empty string in a control means "leave it to the assistant" (stored as null). */
function toStored(value: string): string | null {
  return value === '' ? null : value;
}

function initialValues(override: PersonOverrideRow | null): OverrideValues {
  return {
    status: override?.status ?? null,
    waiting_on: override?.waiting_on ?? null,
    next_action: override?.next_action ?? null,
    due_date: override?.due_date ?? null,
    person_type: override?.person_type ?? null,
    note: override?.note ?? null,
  };
}

/** The "Correct this" form on a person's page. */
export function OverrideForm({
  override,
  vocabulary,
  onSave,
  onClear,
  isSaving,
  isClearing,
}: OverrideFormProps) {
  const [values, setValues] = useState<OverrideValues>(() => initialValues(override));
  const busy = isSaving || isClearing;

  function update<K extends keyof OverrideValues>(key: K, value: OverrideValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        // A correction with every field left to the assistant is no correction:
        // storing it would keep "Corrected by you" showing over nothing.
        if (hasAnyOverride(values)) {
          onSave(values);
          return;
        }
        onClear();
      }}
    >
      <p className="text-sm text-ink-muted">{copy.override.intro}</p>

      <OverrideSelect
        label={copy.override.statusLabel}
        value={values.status}
        options={contactStatusSchema.options}
        labels={vocabulary.statusLabels}
        onChange={(next) => {
          update('status', next);
        }}
      />

      <OverrideSelect
        label={copy.override.waitingOnLabel}
        value={values.waiting_on}
        options={waitingOnSchema.options}
        labels={copy.waitingOnLabels}
        onChange={(next) => {
          update('waiting_on', next);
        }}
      />

      <CategorySelect
        categories={vocabulary.categories}
        saved={override?.person_type ?? null}
        value={values.person_type}
        onChange={(next) => {
          update('person_type', next);
        }}
      />

      <LabelledField label={copy.override.nextActionLabel}>
        {(id) => (
          <input
            id={id}
            type="text"
            className={fieldClassName}
            value={values.next_action ?? ''}
            onChange={(event) => {
              update('next_action', toStored(event.target.value));
            }}
          />
        )}
      </LabelledField>

      <LabelledField label={copy.override.dueDateLabel}>
        {(id) => (
          <input
            id={id}
            type="date"
            className={fieldClassName}
            value={values.due_date ?? ''}
            onChange={(event) => {
              update('due_date', toStored(event.target.value));
            }}
          />
        )}
      </LabelledField>

      <LabelledField label={copy.override.noteLabel}>
        {(id) => (
          <textarea
            id={id}
            rows={3}
            className={fieldClassName}
            value={values.note ?? ''}
            onChange={(event) => {
              update('note', toStored(event.target.value));
            }}
          />
        )}
      </LabelledField>

      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" disabled={busy}>
          {isSaving ? copy.override.saving : copy.override.save}
        </Button>
        {override !== null && (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => {
              setValues(initialValues(null));
              onClear();
            }}
          >
            {isClearing ? copy.override.clearing : copy.override.clear}
          </Button>
        )}
      </div>
    </form>
  );
}
