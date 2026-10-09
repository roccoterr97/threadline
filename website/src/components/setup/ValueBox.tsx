import { CopyButton } from '../CopyButton';

interface ValueBoxProps {
  value: string;
  /** What the value is, for the copy button's name: "the dashboard address". */
  what: string;
}

/** A value to copy as it is, with a button that copies it. */
export function ValueBox({ value, what }: ValueBoxProps) {
  return (
    <div className="flex items-center gap-3 rounded-token-md border border-line bg-neutral-soft px-3 py-2">
      <span className="min-w-0 flex-1 break-all font-mono text-sm text-ink">{value}</span>
      <CopyButton text={value} what={what} />
    </div>
  );
}
