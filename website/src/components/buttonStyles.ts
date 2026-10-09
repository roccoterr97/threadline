/** The shared look of buttons and button-like links. */
export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-token-sm px-4 py-2.5 text-base font-medium transition-[color,background-color,border-color,transform] duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60 disabled:active:translate-y-0';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover',
  secondary: 'border border-line-strong bg-transparent text-ink hover:border-ink',
  quiet: 'link',
};

export function buttonClasses(variant: ButtonVariant, extra = ''): string {
  return `${BASE} ${VARIANTS[variant]} ${extra}`.trim();
}
