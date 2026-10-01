import { NavLink } from 'react-router-dom';
import * as copy from '../copy/en';
import { Icon } from './Icon';
import { NAV_ITEMS } from './navItems';
import { ReviewCount } from './ReviewCount';

interface HeaderNavProps {
  /** Open questions waiting on the review page. */
  reviewCount: number;
}

function linkClass({ isActive }: { isActive: boolean }): string {
  const base =
    'inline-flex min-h-11 items-center gap-2 rounded-token-md px-3 py-2 text-sm font-medium transition-colors';
  return isActive ? `${base} bg-accent text-accent-fg` : `${base} text-ink hover:bg-neutral-soft`;
}

/**
 * The main menu inside the header, from tablet width up. On a phone the same
 * links live in the bottom bar instead, so the header never wraps.
 */
export function HeaderNav({ reviewCount }: HeaderNavProps) {
  return (
    <nav aria-label={copy.nav.headerLabel} className="hidden items-center gap-1 md:flex">
      {NAV_ITEMS.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
          <Icon name={item.icon} className="h-4 w-4" />
          {item.label}
          {item.showsReviewCount && <ReviewCount count={reviewCount} />}
        </NavLink>
      ))}
    </nav>
  );
}
