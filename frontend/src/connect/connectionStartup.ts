import { parseConnectFragment, withoutConnectValues, type ConnectLink } from '../lib/connectLink';
import { hasFixedSettings, type SupabaseSettings } from '../lib/runtimeConfig';
import { readSavedConnection, saveConnection } from '../lib/savedConnection';

/**
 * What the page does with a personal link it was opened with, decided once,
 * before the database client starts: that client also reads the address after
 * a sign-in, so the link's own values must be gone from it by then.
 */

/** What to do with the link. */
export type LinkAction =
  /** No link, or a page whose database is fixed by `config.js` or the build. */
  | { kind: 'keep' }
  /** A link to the database already in use, or the first one: use it. */
  | { kind: 'save'; settings: SupabaseSettings }
  /** A link to a different database than the one saved: ask first. */
  | { kind: 'confirm'; current: SupabaseSettings; incoming: SupabaseSettings }
  /** A link whose values are not a project and a public key. */
  | { kind: 'invalid' };

/** How the page starts, once the link is dealt with. */
export type StartupState =
  | { kind: 'ready' }
  | { kind: 'invalid-link' }
  | { kind: 'confirm-switch'; current: SupabaseSettings; incoming: SupabaseSettings };

/**
 * Decides what a link does.
 *
 * @param link - What the address held.
 * @param saved - The database a link saved before, if any.
 * @param fixed - Whether `config.js` or the build already names the database.
 */
export function decideLinkAction(
  link: ConnectLink,
  saved: SupabaseSettings | null,
  fixed: boolean,
): LinkAction {
  if (link.kind === 'none' || fixed) return { kind: 'keep' };
  if (link.kind === 'invalid') return { kind: 'invalid' };
  if (saved === null || saved.url === link.settings.url) {
    return { kind: 'save', settings: link.settings };
  }
  return { kind: 'confirm', current: saved, incoming: link.settings };
}

/**
 * Takes the link's values out of the address bar, leaving everything else.
 *
 * @returns What the address held.
 */
export function takeConnectLink(): ConnectLink {
  const { hash, pathname, search } = window.location;
  const link = parseConnectFragment(hash);
  if (link.kind === 'none') return link;
  const rest = withoutConnectValues(hash);
  const address = `${pathname}${search}${rest === '' ? '' : `#${rest}`}`;
  window.history.replaceState(window.history.state, '', address);
  return link;
}

/** Deals with the link the page was opened with, if any, and says how to start. */
export function startConnection(): StartupState {
  const action = decideLinkAction(takeConnectLink(), readSavedConnection(), hasFixedSettings());
  switch (action.kind) {
    case 'keep':
      return { kind: 'ready' };
    case 'save':
      saveConnection(action.settings);
      return { kind: 'ready' };
    case 'invalid':
      return { kind: 'invalid-link' };
    case 'confirm':
      return { kind: 'confirm-switch', current: action.current, incoming: action.incoming };
  }
}

/**
 * Starts the page again when a personal link is opened in a tab already
 * showing the dashboard: only the part after `#` changes then, which does not
 * reload the page, and the database client in use belongs to the old address.
 */
export function restartOnNewLink(): void {
  window.addEventListener('hashchange', () => {
    if (parseConnectFragment(window.location.hash).kind !== 'none') window.location.reload();
  });
}
