interface LoadingStateProps {
  /** What is being loaded, in plain words. */
  label: string;
}

/** Shown while a screen is fetching. Announced politely to screen readers. */
export function LoadingState({ label }: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-token-lg border border-line bg-surface p-6 text-center text-ink-muted"
    >
      {label}
    </div>
  );
}
