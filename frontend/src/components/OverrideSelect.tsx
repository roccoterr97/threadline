import * as copy from '../copy/en';
import { fieldClassName, LabelledField } from './LabelledField';

interface OverrideSelectProps<T extends string> {
  label: string;
  /** Null means "leave it to the assistant". */
  value: T | null;
  options: readonly T[];
  labels: Record<T, string>;
  onChange: (next: T | null) => void;
}

/**
 * A closed-list field on the correction form.
 *
 * The empty option is not a value: it means the owner has not overridden this
 * field, so the assistant's own answer keeps applying.
 */
export function OverrideSelect<T extends string>({
  label,
  value,
  options,
  labels,
  onChange,
}: OverrideSelectProps<T>) {
  return (
    <LabelledField label={label}>
      {(id) => (
        <select
          id={id}
          className={fieldClassName}
          value={value ?? ''}
          onChange={(event) => {
            const next = options.find((option) => option === event.target.value);
            onChange(next ?? null);
          }}
        >
          <option value="">{copy.override.keepAssistantValue}</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {labels[option]}
            </option>
          ))}
        </select>
      )}
    </LabelledField>
  );
}
