import { Link, useLocation } from 'react-router-dom';
import * as copy from '../copy/en';
import { organisationPath, organisationsListState } from '../lib/organisationAddress';

interface OrganisationLinkProps {
  /** The organisation's name, or null for the people with none on record. */
  name: string | null;
  className: string;
}

/**
 * A link to one organisation's page. It takes the list's filters and order
 * along, so the way back returns to the same view.
 */
export function OrganisationLink({ name, className }: OrganisationLinkProps) {
  const { search } = useLocation();
  return (
    <Link to={organisationPath(name)} state={organisationsListState(search)} className={className}>
      {name ?? copy.organisations.noOrganisation}
    </Link>
  );
}
