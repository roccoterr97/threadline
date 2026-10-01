import type { ReactNode } from 'react';
import * as copy from '../copy/en';
import { ANY, type TypeFilter } from '../domain/peopleView';
import type { Category } from '../types/database';
import { TypeDot } from './TypeDot';

const CHIP =
  'inline-flex min-h-11 items-center gap-2 rounded-token-md border px-3 py-2 text-sm font-medium transition-colors';
const CHIP_SELECTED = 'border-accent bg-accent text-accent-fg';
const CHIP_IDLE = 'border-line-strong bg-surface text-ink hover:bg-neutral-soft';

interface FilterChipsProps {
  value: TypeFilter;
  /** The categories to offer, in order; "Everyone" is always added first. */
  categories: readonly Category[];
  onChange: (next: TypeFilter) => void;
}

interface ChipProps {
  selected: boolean;
  onSelect: () => void;
  children: ReactNode;
}

function Chip({ selected, onSelect, children }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`${CHIP} ${selected ? CHIP_SELECTED : CHIP_IDLE}`}
    >
      {children}
    </button>
  );
}

/**
 * The row of chips that picks which category of contact to show.
 *
 * The chosen chip is marked with `aria-pressed` as well as a colour, so the
 * selection is never conveyed by colour alone. Each category carries a dot in
 * its own colour, matching its badges and the grid's column heads. The chips
 * wrap onto more lines when there are many, so the page never scrolls sideways.
 */
export function FilterChips({ value, categories, onChange }: FilterChipsProps) {
  return (
    <div role="group" aria-label={copy.home.filtersLabel} className="flex flex-wrap gap-2">
      <Chip
        selected={value === ANY}
        onSelect={() => {
          onChange(ANY);
        }}
      >
        {copy.filterLabels.everyone}
      </Chip>
      {categories.map((category) => (
        <Chip
          key={category.key}
          selected={value === category.key}
          onSelect={() => {
            onChange(category.key);
          }}
        >
          <TypeDot colour={category.colour} />
          {category.group_label}
        </Chip>
      ))}
    </div>
  );
}
