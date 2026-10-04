import type { Location } from 'react-router-dom';
import { z } from 'zod';
import * as copy from '../copy/en';
import {
  organisationPath,
  readOrganisationPath,
  readOrganisationsListState,
  type OrganisationsListState,
} from './organisationAddress';
import { PEOPLE_PATH, peopleListAddress, peopleListState } from './peopleListAddress';

/**
 * A person can be opened from the People page or from an organisation's page.
 * The link takes a note of which along in the router's location state, so
 * every way back from the person returns to the list it was opened from.
 */

const organisationOriginSchema = z.object({
  organisation: z.object({ name: z.string().min(1).nullable() }),
});

/**
 * The location state for a link to a person shown on the page at `location`:
 * the People page's filters, or the organisation page together with what
 * that page remembers of its own way back. Nothing for any other page.
 */
export function personLinkState(
  location: Pick<Location<unknown>, 'pathname' | 'search' | 'state'>,
): object | undefined {
  if (location.pathname === PEOPLE_PATH) return peopleListState(location.search);
  const organisation = readOrganisationPath(location.pathname);
  if (organisation === null) return undefined;
  return { organisation, ...readOrganisationsListState(location.state) };
}

/** The list a person was opened from. */
export interface PersonOrigin {
  /** Where every way back from the person goes. */
  address: string;
  /** What that address is opened with, so its own way back still works. */
  state: OrganisationsListState | undefined;
  /** What the link back says. */
  label: string;
}

/**
 * Where to go back to from a person: the organisation page a location state
 * names, or the People page (with any filters the state carries) for every
 * other state. The address is built from the organisation's name alone, so
 * it always stays inside the dashboard.
 */
export function personOrigin(state: unknown): PersonOrigin {
  const parsed = organisationOriginSchema.safeParse(state);
  if (!parsed.success) {
    return { address: peopleListAddress(state), state: undefined, label: copy.person.backToPeople };
  }
  const { name } = parsed.data.organisation;
  return {
    address: organisationPath(name),
    state: readOrganisationsListState(state),
    label:
      name === null
        ? copy.organisations.backToNoOrganisation
        : copy.organisations.backToOrganisation(name),
  };
}
