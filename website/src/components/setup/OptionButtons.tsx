export interface Option {
  id: string;
  label: string;
  hint?: string;
}

interface OptionButtonsProps {
  question: string;
  options: readonly Option[];
  value: string | undefined;
  onChange: (id: string) => void;
}

/** One question, answered by pressing one of a few big buttons, each with a dot that fills when chosen. */
export function OptionButtons({ question, options, value, onChange }: OptionButtonsProps) {
  return (
    <div role="radiogroup" aria-label={question} className="grid gap-3">
      {options.map((option) => {
        const selected = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.id)}
            className={`flex items-start gap-4 rounded-token-md border bg-surface px-5 py-4 text-left transition-[border-color,box-shadow] duration-150 ${
              selected
                ? 'border-accent shadow-[inset_0_0_0_1px_var(--tracker-accent)]'
                : 'border-line hover:border-line-strong'
            }`}
          >
            <span
              aria-hidden="true"
              className={`mt-1.5 grid size-4 shrink-0 place-items-center rounded-full border-2 transition-colors ${
                selected ? 'border-accent' : 'border-line-strong'
              }`}
            >
              <span
                className={`size-2 rounded-full bg-accent transition-transform duration-150 ${selected ? 'scale-100' : 'scale-0'}`}
              />
            </span>
            <span>
              <span className="block font-display text-lg font-semibold text-ink">{option.label}</span>
              {option.hint !== undefined && <span className="mt-1 block text-sm text-ink-muted">{option.hint}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
