import type { ReactNode } from 'react';

export interface ThreadItem {
  id: string;
  title: string;
  text: ReactNode;
}

/**
 * The site's motif at a small scale: one line with a dot per moment, the
 * dashboard's timeline drawn large. Used wherever things happen in order.
 */
export function Thread({ items }: { items: readonly ThreadItem[] }) {
  return (
    <ol className="thread-list">
      {items.map((item, index) => (
        <li key={item.id} className="node">
          <h3 className="text-xl text-ink">
            <span className="label-number font-sans text-base tabular-nums">{String(index + 1).padStart(2, '0')}</span>
            {item.title}
          </h3>
          <div className="mt-3 max-w-[44rem] space-y-3 text-ink-muted">{item.text}</div>
        </li>
      ))}
    </ol>
  );
}
