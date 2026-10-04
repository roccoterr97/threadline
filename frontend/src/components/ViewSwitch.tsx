import { NavLink } from 'react-router-dom';
import * as copy from '../copy/en';
import { ORGANISATIONS_PATH } from '../lib/organisationAddress';
import { PEOPLE_PATH } from '../lib/peopleListAddress';

const LINK =
  'inline-flex min-h-11 flex-1 items-center justify-center rounded-token-md border px-3 py-2 text-sm font-medium transition-colors';
const LINK_SELECTED = 'border-accent bg-accent text-accent-fg';
const LINK_IDLE = 'border-line-strong bg-surface text-ink hover:bg-neutral-soft';

function linkClass({ isActive }: { isActive: boolean }): string {
  return `${LINK} ${isActive ? LINK_SELECTED : LINK_IDLE}`;
}

/**
 * The phone's way between the People page and the organisations page. The
 * bottom bar has room for four pages, so the two views of the same list
 * share its first place and this switch sits at the top of both. From tablet
 * width up the header menu lists both pages and the switch is not drawn.
 * The current view is marked as the current page, never by colour alone.
 */
export function ViewSwitch() {
  return (
    <nav aria-label={copy.organisations.switchLabel} className="flex gap-2 md:hidden">
      <NavLink to={PEOPLE_PATH} end className={linkClass}>
        {copy.nav.home}
      </NavLink>
      <NavLink to={ORGANISATIONS_PATH} end className={linkClass}>
        {copy.nav.organisations}
      </NavLink>
    </nav>
  );
}
