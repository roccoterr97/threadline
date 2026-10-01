import { useId, type ReactNode } from 'react';

interface LabelledFieldProps {
  label: string;
  /** Receives the id to put on the input, so the label always matches it. */
  children: (fieldId: string) => ReactNode;
}

/** A form control with a label that is always wired to it. */
export function LabelledField({ label, children }: LabelledFieldProps) {
  const fieldId = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={fieldId} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children(fieldId)}
    </div>
  );
}

/** Shared look for every text, date, select and textarea control; a field at fault gets a red edge. */
export const fieldClassName =
  'min-h-11 w-full rounded-token-md border border-line-strong bg-surface px-3 py-2 text-base text-ink aria-invalid:border-2 aria-invalid:border-danger';
