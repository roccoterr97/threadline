/**
 * The note the person page leaves for the people list after hiding someone,
 * carried in the router's location state so the list can say what happened.
 */

/** Who was just hidden. */
export interface HiddenPerson {
  id: string;
  name: string;
}

interface HiddenPersonState {
  hiddenPerson: HiddenPerson;
}

/** The location state to navigate with after hiding `person`. */
export function hiddenPersonState(person: HiddenPerson): HiddenPersonState {
  return { hiddenPerson: person };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** The person a location state says was just hidden, or null for any other state. */
export function readHiddenPerson(state: unknown): HiddenPerson | null {
  if (!isRecord(state) || !isRecord(state.hiddenPerson)) return null;
  const { id, name } = state.hiddenPerson;
  return typeof id === 'string' && typeof name === 'string' ? { id, name } : null;
}

/**
 * The same location state without the "just hidden" note, so clearing the
 * note keeps whatever else the page was opened with (an organisation page
 * remembers its way back there). Null when nothing else is left.
 */
export function withoutHiddenPerson(state: unknown): Record<string, unknown> | null {
  if (!isRecord(state)) return null;
  const { hiddenPerson: _note, ...rest } = state;
  return Object.keys(rest).length === 0 ? null : rest;
}
