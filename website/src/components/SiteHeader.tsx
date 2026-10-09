import { Link, NavLink } from 'react-router-dom';
import { DEMO_URL } from '../constants/links';
import * as copy from '../copy/en';
import { buttonClasses } from './buttonStyles';
import { Logo } from './Logo';
import { OutsideMark } from './OutsideMark';

const LINK =
  'inline-flex items-center gap-1 py-1 text-sm font-medium text-ink decoration-accent decoration-2 underline-offset-[0.45em] hover:text-accent aria-[current=page]:text-accent aria-[current=page]:underline';

/**
 * The bar at the top of every page. On a phone: the mark and the set-up on
 * one row, the two other ways in on a quiet row beneath. Wider: one row.
 */
export function SiteHeader() {
  return (
    <header className="site-container">
      <div className="grid grid-cols-[1fr_auto] items-center gap-y-3 py-4 md:flex md:gap-x-7 md:py-6">
        <Link to="/" className="flex items-center gap-2.5 justify-self-start font-display text-lg font-semibold text-ink md:mr-auto">
          <Logo />
          {copy.site.name}
        </Link>
        <nav
          aria-label={copy.nav.label}
          className="col-span-2 row-start-2 flex gap-6 border-t border-line pt-3 md:border-0 md:pt-0"
        >
          <a href={DEMO_URL} className={LINK} target="_blank" rel="noreferrer">
            {copy.nav.demo}
            <OutsideMark />
          </a>
          <NavLink to="/app" className={LINK}>
            {copy.nav.dashboard}
          </NavLink>
        </nav>
        <NavLink to="/setup" className={buttonClasses('primary', 'col-start-2 row-start-1 px-3.5 py-1.5 text-sm')}>
          {copy.nav.setup}
        </NavLink>
      </div>
    </header>
  );
}
