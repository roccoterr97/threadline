import { z } from 'zod';

/**
 * Where the organisations pages live, and the way back to the list.
 *
 * An organisation has no ID the dashboard can read, so its page is addressed
 * by its name; the people with no organisation get an address of their own
 * that no name can take. The list's filters and order live in its address,
 * and an organisation opened from it carries that query in the router's
 * location state, so the way back returns to the same view.
 */

/** Where the organisations list lives. */
export const ORGANISATIONS_PATH = '/organisations';

/** The route of one organisation's page; the name is the `organisationName` parameter. */
export const ORGANISATION_ROUTE = `${ORGANISATIONS_PATH}/name/:organisationName`;

/** The page of the people who have no organisation on record. */
export const NO_ORGANISATION_PATH = `${ORGANISATIONS_PATH}/none`;

const NAMED_PREFIX = `${ORGANISATIONS_PATH}/name/`;

/** The page of the organisation called `name`, or of the people with none for null. */
export function organisationPath(name: string | null): string {
  return name === null ? NO_ORGANISATION_PATH : `${NAMED_PREFIX}${encodeURIComponent(name)}`;
}

/** Which organisation's page a path is. */
export interface OrganisationPage {
  /** The organisation's name, or null on the page of the people with none. */
  name: string | null;
}

function decodeName(encoded: string): string | null {
  try {
    return decodeURIComponent(encoded);
  } catch (error) {
    // A stray "%" that is not an escape: no page has such an address.
    if (!(error instanceof URIError)) throw error;
    return null;
  }
}

/** The organisation page `pathname` is, or null for any other address. */
export function readOrganisationPath(pathname: string): OrganisationPage | null {
  const path = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
  if (path === NO_ORGANISATION_PATH) return { name: null };
  if (!path.startsWith(NAMED_PREFIX)) return null;
  const encoded = path.slice(NAMED_PREFIX.length);
  if (encoded === '' || encoded.includes('/')) return null;
  const name = decodeName(encoded);
  return name === null ? null : { name };
}

const organisationsListStateSchema = z.object({
  organisationsSearch: z.string().startsWith('?'),
});

/** What an organisation page remembers about the list it was opened from. */
export type OrganisationsListState = z.infer<typeof organisationsListStateSchema>;

/** The location state for a link opened from the organisations list showing `search`. */
export function organisationsListState(search: string): OrganisationsListState {
  return { organisationsSearch: search };
}

/** The list view a location state carries, or undefined for any other state. */
export function readOrganisationsListState(state: unknown): OrganisationsListState | undefined {
  const parsed = organisationsListStateSchema.safeParse(state);
  return parsed.success ? parsed.data : undefined;
}

/**
 * The organisations list address to go back to: with the filters a location
 * state carries, or the plain list for any other state. Only a query is taken
 * from the state, so the address always stays on the organisations list.
 */
export function organisationsListAddress(state: unknown): string {
  const kept = readOrganisationsListState(state);
  return kept === undefined ? ORGANISATIONS_PATH : `${ORGANISATIONS_PATH}${kept.organisationsSearch}`;
}
