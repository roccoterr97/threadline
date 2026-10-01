import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  body: string;
  /** Optional way out, e.g. a button that clears the filter. */
  action?: ReactNode;
}

/** Shown when a screen loaded fine but there is genuinely nothing to show. */
export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <div className="rounded-token-lg border border-dashed border-line bg-surface p-6 text-center">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-prose text-ink-muted">{body}</p>
      {action !== undefined && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
