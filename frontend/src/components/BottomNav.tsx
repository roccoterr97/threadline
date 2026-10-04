import { Link, useLocation } from 'react-router-dom';
import * as copy from '../copy/en';
import { Icon } from './Icon';
import { BOTTOM_NAV_ITEMS, currentNavPath } from './navItems';
import { ReviewCount } from './ReviewCount';

interface BottomNavProps {
  /** Open questions waiting on the review page. */
  reviewCount: number;
}

function linkClass(isActive: boolean): string {
  const base =
    'relative flex min-h-14 flex-col items-center justify-center gap-1 px-2 py-1.5 text-xs transition-colors';
  return isActive
    ? `${base} font-semibold text-accent`
    : `${base} font-medium text-ink-muted hover:text-ink`;
}

function iconClass(isActive: boolean): string {
  const base = 'flex h-7 w-12 items-center justify-center rounded-full';
  return isActive ? `${base} bg-neutral-soft` : base;
}

/**
 * The main menu as a bar fixed to the bottom of a phone screen, within thumb
 * reach. Each link is an icon above a short label; the current page is marked
 * by colour, weight and a pill behind its icon, and announced as the current
 * page (see `currentNavPath`). The bar keeps clear of the phone's home indicator.
 */
export function BottomNav({ reviewCount }: BottomNavProps) {
  const current = currentNavPath(useLocation());
  return (
    <nav
      aria-label={copy.nav.bottomBarLabel}
      className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="m-0 grid list-none grid-cols-4 p-0">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const isActive = item.to === current;
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                aria-current={isActive ? 'page' : undefined}
                className={linkClass(isActive)}
              >
                <span className={iconClass(isActive)}>
                  <Icon name={item.icon} />
                </span>
                {item.label}
                {/* After the label so it is read second, but drawn on the icon's corner. */}
                {item.showsReviewCount && (
                  <ReviewCount
                    count={reviewCount}
                    className="absolute top-0.5 left-[calc(50%+0.75rem)]"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
