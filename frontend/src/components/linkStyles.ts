/**
 * Shared looks for text links, so the phone-sized tap targets are decided in
 * one place.
 */

/** The look of every plain link in running text. */
export const TEXT_LINK = 'text-accent underline underline-offset-2';

/**
 * A text link that stands alone on its own line (a way back, a way out of an
 * empty page). It is as tall as a button, so a thumb can hit it.
 */
export const TAP_LINK = `inline-flex min-h-11 items-center ${TEXT_LINK}`;

/**
 * The name on a list card, as a link whose clickable area stretches over the
 * whole card (the card must be `relative`). Nothing else on the card is a
 * link, so the whole card becomes one big, thumb-sized target.
 */
export const CARD_LINK = `text-lg font-semibold break-words ${TEXT_LINK} after:absolute after:inset-0 after:content-['']`;
