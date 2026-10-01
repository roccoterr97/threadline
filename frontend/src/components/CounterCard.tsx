import { Link } from 'react-router-dom';
import * as copy from '../copy/en';

interface CounterCardProps {
  label: string;
  value: number;
  /** The address that shows exactly the people this number counts. */
  to: string;
  /** True when the list below is already showing these people. */
  isShown: boolean;
}

/**
 * One of the headline numbers on the home page, as a link to the people behind
 * it. The one being shown is marked with `aria-current`, a thicker ring and a
 * line of text, so the choice never rests on colour alone.
 */
export function CounterCard({ label, value, to, isShown }: CounterCardProps) {
  return (
    <li className="flex">
      <Link
        to={to}
        aria-current={isShown ? 'true' : undefined}
        className={`flex min-h-11 w-full flex-col rounded-token-lg border bg-surface p-4 shadow-card transition-colors hover:border-accent ${
          isShown ? 'border-accent ring-2 ring-accent' : 'border-line'
        }`}
      >
        <span className="text-sm font-medium text-ink-muted">{label}</span>
        <span className="mt-1 text-3xl font-semibold tabular-nums text-ink">{value}</span>
        {isShown && (
          <span className="mt-1 text-xs font-semibold text-accent">{copy.home.counterShown}</span>
        )}
      </Link>
    </li>
  );
}
