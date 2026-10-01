/**
 * Threadline's mark: a tick on a rounded square in the accent colour.
 *
 * Decorative, because the app's name is always printed right next to it.
 */
export function Logo() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 32 32" className="h-8 w-8 shrink-0">
      <rect width="32" height="32" rx="8" className="fill-accent" />
      <path
        d="M9 16.5l4.5 4.5L23 11.5"
        fill="none"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent-fg"
      />
    </svg>
  );
}
