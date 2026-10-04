import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { personLinkState } from '../lib/personOrigin';

interface PersonLinkProps {
  personId: string;
  className: string;
  children: ReactNode;
}

/**
 * A link to one person's page. Opened from the People page, it takes the
 * page's filters and sort along; opened from an organisation's page, it takes
 * that page along. Either way, the way back returns to the same view.
 */
export function PersonLink({ personId, className, children }: PersonLinkProps) {
  const location = useLocation();
  return (
    <Link
      to={`/people/${personId}`}
      state={personLinkState(location)}
      className={className}
    >
      {children}
    </Link>
  );
}
