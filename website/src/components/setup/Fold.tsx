import type { ReactNode } from 'react';

/** Something the reader can open when they need it, closed by default. */
export function Fold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="fold group border-y border-line">
      <summary className="flex cursor-pointer list-none items-center gap-3 py-3.5 font-medium text-ink transition-colors hover:text-accent [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className="size-2 shrink-0 -rotate-45 border-r-2 border-b-2 border-current transition-transform duration-200 group-open:rotate-45"
        />
        {label}
      </summary>
      <div className="pb-5 pl-5">{children}</div>
    </details>
  );
}
