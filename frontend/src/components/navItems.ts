import * as copy from '../copy/en';
import type { IconName } from './Icon';

/** One page in the main menu. */
export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Only highlight on an exact address match (the home page would match every page otherwise). */
  end: boolean;
  /** Shows how many questions are waiting to be answered. */
  showsReviewCount: boolean;
}

/**
 * The main menu, in order. The header (laptop) and the bottom bar (phone) both
 * read this list, so the two can never drift apart.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: copy.nav.home, icon: 'people', end: true, showsReviewCount: false },
  { to: '/review', label: copy.nav.review, icon: 'review', end: false, showsReviewCount: true },
  { to: '/runs', label: copy.nav.runs, icon: 'runs', end: false, showsReviewCount: false },
  {
    to: '/settings',
    label: copy.nav.settings,
    icon: 'settings',
    end: false,
    showsReviewCount: false,
  },
];
