import { useId } from 'react';

interface FilterSelectProps<T extends string> {
  label: string;
  value: T;
  options: readonly T[];
  labels: Record<T, string>;
  onChange: (next: T) => void;
}

/** One closed-list filter above the people list, with its label wired to it. */
export function FilterSelect<T extends string>({
  label,
  value,
  options,
  labels,
  onChange,
}: FilterSelectProps<T>) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="w-20 shrink-0 text-sm font-medium text-ink-muted sm:w-auto">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          const next = options.find((option) => option === event.target.value);
          if (next !== undefined) onChange(next);
        }}
        className="min-h-11 min-w-0 flex-1 rounded-token-md border border-line-strong bg-surface px-3 py-2 text-base text-ink sm:flex-none"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {labels[option]}
          </option>
        ))}
      </select>
    </div>
  );
}
