import { useId } from 'react';
import * as copy from '../copy/en';
import { CATEGORY_COLOURS } from '../domain/categorySettings';
import type { CategoryColour } from '../types/database';
import { TypeDot } from './TypeDot';

interface ColourPickerProps {
  value: CategoryColour;
  onChange: (next: CategoryColour) => void;
  disabled?: boolean;
}

/**
 * The nine palette colours as a group of radio buttons. Each one shows its
 * swatch and its name, so the choice never rests on colour alone.
 */
export function ColourPicker({ value, onChange, disabled = false }: ColourPickerProps) {
  const name = useId();
  return (
    <fieldset className="m-0 flex flex-col gap-1 border-0 p-0" disabled={disabled}>
      <legend className="mb-1 p-0 text-sm font-medium text-ink">
        {copy.categorySettings.fields.colour}
      </legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {CATEGORY_COLOURS.map((colour) => (
          <label
            key={colour}
            className="flex min-h-11 cursor-pointer items-center gap-2 rounded-token-md border border-line px-3 py-2 text-sm text-ink hover:bg-neutral-soft"
          >
            <input
              type="radio"
              name={name}
              value={colour}
              checked={value === colour}
              onChange={() => {
                onChange(colour);
              }}
              className="h-4 w-4 accent-accent"
            />
            <TypeDot colour={colour} />
            {copy.categoryColourNames[colour]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
