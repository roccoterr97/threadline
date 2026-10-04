import { matchPath, type Location } from 'react-router-dom';
import * as copy from '../copy/en';
import { ORGANISATIONS_PATH } from '../lib/organisationAddress';
import { personOrigin } from '../lib/personOrigin';
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
  /**
   * False for a page the phone's bottom bar has no room for. Such a page is
   * reached from the People page there instead (see `ViewSwitch`).
   */
  inBottomBar: boolean;
}

/**
 * The main menu, in order. The header (laptop) and the bottom bar (phone) both
 * read this list, so the two can never drift apart.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  {
    to: '/',
    label: copy.nav.home,
    icon: 'people',
    end: true,
    showsReviewCount: false,
    inBottomBar: true,
  },
  {
    to: ORGANISATIONS_PATH,
    label: copy.nav.organisations,
    icon: 'organisations',
    end: false,
    showsReviewCount: false,
    inBottomBar: false,
  },
  {
    to: '/review',
    label: copy.nav.review,
    icon: 'review',
    end: false,
    showsReviewCount: true,
    inBottomBar: true,
  },
  {
    to: '/runs',
    label: copy.nav.runs,
    icon: 'runs',
    end: false,
    showsReviewCount: false,
    inBottomBar: true,
  },
  {
    to: '/settings',
    label: copy.nav.settings,
    icon: 'settings',
    end: false,
    showsReviewCount: false,
    inBottomBar: true,
  },
];

/** The pages the phone's bottom bar lists: four, one per column. */
export const BOTTOM_NAV_ITEMS: readonly NavItem[] = NAV_ITEMS.filter((item) => item.inBottomBar);

const PERSON_ROUTE = '/people/:personId';

function isUnder(pathname: string, item: NavItem): boolean {
  if (pathname === item.to) return true;
  return !item.end && pathname.startsWith(`${item.to}/`);
}

/**
 * The `to` of the menu item to mark as the current page, or null when none
 * is. A page in the menu marks itself, and so does every page under it. A
 * person's page marks the list it was opened from: People, or Organisations
 * when it was opened from an organisation's page.
 */
export function currentNavPath(location: Pick<Location<unknown>, 'pathname' | 'state'>): string | null {
  if (matchPath(PERSON_ROUTE, location.pathname) !== null) {
    const origin = personOrigin(location.state);
    return origin.address.startsWith(ORGANISATIONS_PATH) ? ORGANISATIONS_PATH : '/';
  }
  return NAV_ITEMS.find((item) => isUnder(location.pathname, item))?.to ?? null;
}
