import type { ReactNode } from 'react';

interface InfoNoteProps {
  children: ReactNode;
}

/** A quiet boxed sentence that explains something about what the page shows. */
export function InfoNote({ children }: InfoNoteProps) {
  return <p className="rounded-token-md border border-line bg-neutral-soft p-3 text-sm text-ink">{children}</p>;
}
