/**
 * The looks of the one button in the app, shared with the few links that must
 * look like a button (a link that leaves the dashboard). Keyboard focus comes
 * from the global focus style; the 44px touch target is set here.
 */

export type ButtonVariant = 'primary' | 'secondary' | 'danger';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover border border-transparent',
  secondary: 'bg-surface text-ink border border-line-strong hover:bg-neutral-soft',
  danger: 'bg-danger-soft text-danger border border-danger hover:opacity-90',
};

/** Every class a button of one variant carries. */
export function buttonClasses(variant: ButtonVariant): string {
  return `inline-flex min-h-11 items-center justify-center gap-2 rounded-token-md px-4 py-2 text-base font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${VARIANT_CLASSES[variant]}`;
}
