import { z } from 'zod';

/**
 * The People page's filters and sort live in its address. A person opened
 * from that page carries the address's query in the router's location state,
 * so hiding the person goes back to the same view rather than to the whole
 * list in its usual order.
 */

/** Where the People page lives. */
export const PEOPLE_PATH = '/';

const peopleListStateSchema = z.object({ peopleSearch: z.string().startsWith('?') });

/** The location state for a link opened from the People page showing `search`. */
export function peopleListState(search: string): { peopleSearch: string } {
  return { peopleSearch: search };
}

/**
 * The People page address to go back to: with the filters a location state
 * carries, or the plain page for any other state. Only a query is taken from
 * the state, so the address always stays on the People page.
 */
export function peopleListAddress(state: unknown): string {
  const parsed = peopleListStateSchema.safeParse(state);
  return parsed.success ? `${PEOPLE_PATH}${parsed.data.peopleSearch}` : PEOPLE_PATH;
}
