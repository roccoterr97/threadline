import { z } from 'zod';
import { SCROLL_PLACES_KEPT } from '../constants/dashboard';
import { logWarning } from './logger';

/**
 * How far down each visited page was scrolled, kept for the browser tab, so
 * Back still finds the place after the page has been reloaded. Only history
 * entry keys, page paths and pixel offsets are stored: a path holds at most a
 * person's ID, which the tab's own history already has, never a name.
 */

const STORAGE_KEY = 'threadline.scroll-positions';

const storedPositionsSchema = z.record(z.string(), z.number());

/** The positions kept for this tab, or none when there are none or they cannot be read. */
export function loadScrollPositions(): Map<string, number> {
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    if (stored === null) return new Map();
    const parsed = storedPositionsSchema.safeParse(JSON.parse(stored));
    return new Map(parsed.success ? Object.entries(parsed.data).slice(-SCROLL_PLACES_KEPT) : []);
  } catch (error) {
    // Storage switched off by the browser, or a value that is not JSON: Back
    // then works from memory alone, as it did before the page was reloaded.
    if (!(error instanceof DOMException || error instanceof SyntaxError)) throw error;
    logWarning('scroll_positions.not_read', { reason: error.name });
    return new Map();
  }
}

/**
 * Writes down where `place` is scrolled, as the newest place, and lets the
 * oldest go once more than SCROLL_PLACES_KEPT are kept.
 */
export function recordScrollPosition(
  positions: Map<string, number>,
  place: string,
  top: number,
): void {
  positions.delete(place);
  positions.set(place, top);
  for (const oldest of positions.keys()) {
    if (positions.size <= SCROLL_PLACES_KEPT) return;
    positions.delete(oldest);
  }
}

/** Keeps the positions for this tab; a full or switched-off storage only costs the reload case. */
export function saveScrollPositions(positions: ReadonlyMap<string, number>): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(positions)));
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
    logWarning('scroll_positions.not_saved', { reason: error.name });
  }
}
