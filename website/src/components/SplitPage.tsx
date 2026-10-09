import type { ReactNode } from 'react';

interface SplitPageProps {
  title: string;
  /** The sentence under the title that says what the page is for. */
  lead?: ReactNode;
  /** More for the left side under the lead: a button, a list of the page's sections. */
  aside?: ReactNode;
  children: ReactNode;
}

/**
 * A page in two halves across the full width: the title and what the page
 * is for on the left, staying in view while the right side is read. On a
 * phone the halves stack.
 */
export function SplitPage({ title, lead, aside, children }: SplitPageProps) {
  return (
    <div className="site-container grid gap-10 pt-10 pb-8 sm:pt-14 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-[clamp(3rem,6vw,8rem)] lg:pt-20">
      <header className="lg:sticky lg:top-10 lg:self-start">
        <h1 className="text-title text-ink">{title}</h1>
        {lead !== undefined && <p className="mt-5 max-w-[34rem] text-lead text-ink-muted">{lead}</p>}
        {aside !== undefined && <div className="mt-8 space-y-4">{aside}</div>}
      </header>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** A titled part of the right-hand side, set off by a line with a dot at its start. */
export function SplitSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="rule-node pt-8 pb-12">
      <h2 className="text-2xl text-ink">{heading}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}
