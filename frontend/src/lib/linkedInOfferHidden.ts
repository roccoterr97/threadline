import { LINKEDIN_OFFER_HIDDEN_KEY } from '../constants/links';
import { logError } from './logger';

/**
 * Whether the owner hid the LinkedIn offer on this browser. Storage can be
 * missing or refused (a private window, blocked site data): then the offer
 * shows again on the next visit, which is harmless.
 */
export function readLinkedInOfferHidden(): boolean {
  try {
    return window.localStorage.getItem(LINKEDIN_OFFER_HIDDEN_KEY) !== null;
  } catch {
    logError('linkedin_offer.read_refused');
    return false;
  }
}

/** Remembers on this browser that the owner hid the LinkedIn offer. */
export function rememberLinkedInOfferHidden(): void {
  try {
    window.localStorage.setItem(LINKEDIN_OFFER_HIDDEN_KEY, '1');
  } catch {
    logError('linkedin_offer.save_refused');
  }
}
