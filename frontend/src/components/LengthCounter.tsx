import * as copy from '../copy/en';

interface LengthCounterProps {
  /** Put on the field's `aria-describedby`, so the count is read with it. */
  id: string;
  length: number;
  max: number;
}

/**
 * How much of a text field's room is used. The field itself stops at `max`,
 * so once it is full a note says why typing does nothing more; that note is
 * announced, while the running count is only read when the field is focused.
 */
export function LengthCounter({ id, length, max }: LengthCounterProps) {
  const atLimit = length >= max;
  return (
    <div className="flex flex-wrap justify-between gap-x-3 text-sm">
      <span role="status" className="font-medium text-warn">
        {atLimit ? copy.categorySettings.length.atLimit(max) : ''}
      </span>
      <span id={id} className="ml-auto text-ink-muted">
        {copy.categorySettings.length.count(length, max)}
      </span>
    </div>
  );
}
