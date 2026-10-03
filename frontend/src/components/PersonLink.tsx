import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { PEOPLE_PATH, peopleListState } from '../lib/peopleListAddress';

interface PersonLinkProps {
  personId: string;
  className: string;
  children: ReactNode;
}

/**
 * A link to one person's page. Opened from the People page, it takes the
 * page's filters and sort along, so the way back returns to the same view.
 */
export function PersonLink({ personId, className, children }: PersonLinkProps) {
  const { pathname, search } = useLocation();
  return (
    <Link
      to={`/people/${personId}`}
      state={pathname === PEOPLE_PATH ? peopleListState(search) : undefined}
      className={className}
    >
      {children}
    </Link>
  );
}
