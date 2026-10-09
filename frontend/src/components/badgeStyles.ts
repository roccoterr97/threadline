import type { CategoryColour, ContactStatus, Signal, WaitingOn } from '../types/database';

/**
 * Which colour each badge value gets — the one place the colour rules live.
 *
 * The rules themselves are written out in `theme/tokens.css`: red is overdue
 * only, amber is "the ball is with the owner", green is a meeting or process
 * running, grey is inactive, and blue is never a state. Something still
 * running with no alarm gets the plain outlined `calm` chip.
 */

/** The meanings a badge can carry. Each one always shows its own text label. */
export type BadgeTone = 'positive' | 'warn' | 'danger' | 'neutral' | 'calm';

/**
 * Shape shared by every badge; the colour classes are added on top. A long
 * label may break anywhere on a phone's cards; in the laptop table it must
 * not, or a column would squeeze a word in two.
 */
export const BADGE_BASE =
  'inline-flex max-w-full items-center gap-1.5 rounded-token-sm border px-2 py-0.5 text-sm font-medium max-lg:wrap-anywhere';

/** The colour classes behind each tone. */
export const TONE_CLASSES: Record<BadgeTone, string> = {
  positive: 'border-transparent bg-positive-soft text-positive',
  warn: 'border-transparent bg-warn-soft text-warn',
  danger: 'border-transparent bg-danger-soft text-danger',
  neutral: 'border-transparent bg-neutral-soft text-neutral',
  calm: 'border-line-strong bg-surface text-ink',
};

/** Where a conversation stands. */
export const STATUS_TONES: Record<ContactStatus, BadgeTone> = {
  contacted_no_reply: 'calm',
  in_conversation: 'calm',
  meeting_planned: 'positive',
  in_process: 'positive',
  gone_quiet: 'warn',
  closed: 'neutral',
};

/** Who owes the next message: the owner is amber, them is calm, nobody is grey. */
export const WAITING_TONES: Record<WaitingOn, BadgeTone> = {
  me: 'warn',
  them: 'calm',
  nobody: 'neutral',
};

/** How warm the conversation feels. A cold one has gone inactive. */
export const SIGNAL_TONES: Record<Signal, BadgeTone> = {
  positive: 'positive',
  neutral: 'calm',
  cold: 'neutral',
};

/*
 * Category colours are keyed by palette slot, not by category: the owner picks
 * a slot for each category. Every class name is written out in full because
 * Tailwind only generates the classes it can read in the source.
 */

/** Soft background and dark text for a category badge, per palette slot. */
export const CATEGORY_BADGE_CLASSES: Record<CategoryColour, string> = {
  violet: 'border-transparent bg-category-violet-soft text-category-violet',
  cyan: 'border-transparent bg-category-cyan-soft text-category-cyan',
  orange: 'border-transparent bg-category-orange-soft text-category-orange',
  pink: 'border-transparent bg-category-pink-soft text-category-pink',
  indigo: 'border-transparent bg-category-indigo-soft text-category-indigo',
  teal: 'border-transparent bg-category-teal-soft text-category-teal',
  olive: 'border-transparent bg-category-olive-soft text-category-olive',
  brown: 'border-transparent bg-category-brown-soft text-category-brown',
  grey: 'border-transparent bg-neutral-soft text-neutral',
};

/** The small solid dot that marks a category on chips and column heads. */
export const CATEGORY_DOT_CLASSES: Record<CategoryColour, string> = {
  violet: 'bg-category-violet',
  cyan: 'bg-category-cyan',
  orange: 'bg-category-orange',
  pink: 'bg-category-pink',
  indigo: 'bg-category-indigo',
  teal: 'bg-category-teal',
  olive: 'bg-category-olive',
  brown: 'bg-category-brown',
  grey: 'bg-neutral',
};
