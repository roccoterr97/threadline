/**
 * Threadline's mark: two threads joining one line, from the owner's logo,
 * drawn in the accent colour.
 *
 * Decorative, because the app's name is always printed right next to it.
 */
export function Logo() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="146 201 264 160"
      fill="none"
      strokeWidth={21}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-8 w-auto shrink-0 stroke-accent"
    >
      <path d="M159 214 H182 C222 214 228 281 268 281" />
      <path d="M159 348 H182 C222 348 228 281 268 281" />
      <path d="M159 281 H397" />
    </svg>
  );
}
