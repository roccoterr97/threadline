import type { SupabaseSettings } from './runtimeConfig';

/**
 * The personal link to the shared dashboard.
 *
 * The shared dashboard is one page for every owner, so by itself it does not
 * know whose database to open. The set-up gives each owner a link that says so
 * after the `#`: `https://app.threadlineapp.com/#project=<ref>&key=<key>`. The
 * browser never sends what follows the `#` to the web host, so the two values
 * stay out of its logs; both are public by design (the same two values a
 * dashboard's own `config.js` carries). The backend writes the link in
 * `backend/src/tracker/domain/dashboard_link.py`.
 */

/** The names of the link's two values, as the backend writes them. */
export const CONNECT_PROJECT_PARAM = 'project';
export const CONNECT_KEY_PARAM = 'key';

/** A project's identifier: the first part of its address. */
const PROJECT_REF = /^[a-z0-9]{8,40}$/;
/** A publishable key (`sb_publishable_...`) or a legacy public key (a JWT). */
const PUBLIC_KEY = /^[A-Za-z0-9._-]{1,4096}$/;
const SECRET_KEY_PREFIX = 'sb_secret_';
/** Roles a legacy key may claim that must never reach a browser. */
const PRIVILEGED_ROLES = new Set(['service_role', 'supabase_admin']);
const JWT_PARTS = 3;

/** What the address's `#` held. */
export type ConnectLink =
  | { kind: 'none' }
  | { kind: 'invalid' }
  | { kind: 'valid'; settings: SupabaseSettings };

/** The database address of a project. */
export function projectAddress(ref: string): string {
  return `https://${ref}.supabase.co`;
}

/** The role a legacy (JWT) key claims, or null when it is not one or unreadable. */
function legacyRole(key: string): string | null {
  const parts = key.split('.');
  if (parts.length !== JWT_PARTS) return null;
  const claims = (parts[1] ?? '').replace(/-/g, '+').replace(/_/g, '/');
  try {
    const decoded: unknown = JSON.parse(atob(claims.padEnd(Math.ceil(claims.length / 4) * 4, '=')));
    if (typeof decoded !== 'object' || decoded === null) return null;
    const role: unknown = Reflect.get(decoded, 'role');
    return typeof role === 'string' ? role : null;
  } catch {
    // Not base64 or not JSON: not a legacy key, so it claims no role at all.
    return null;
  }
}

/** True for a key a browser may hold: a publishable or legacy public key, never a secret one. */
export function isPublicKey(key: string): boolean {
  if (!PUBLIC_KEY.test(key) || key.startsWith(SECRET_KEY_PREFIX)) return false;
  const role = legacyRole(key);
  return role === null || !PRIVILEGED_ROLES.has(role);
}

/** One `name=value` pair of a fragment, decoded; null when it cannot be decoded. */
function decodedPair(part: string): [string, string] | null {
  const split = part.indexOf('=');
  if (split < 0) return null;
  try {
    return [decodeURIComponent(part.slice(0, split)), decodeURIComponent(part.slice(split + 1))];
  } catch {
    // A broken %-sequence: the part is not something this link could have written.
    return null;
  }
}

function isOwnPart(part: string): boolean {
  const name = decodedPair(part)?.[0];
  return name === CONNECT_PROJECT_PARAM || name === CONNECT_KEY_PARAM;
}

/**
 * Reads the link's two values out of what follows the `#`.
 *
 * @param fragment - The address's fragment, with or without its `#`.
 * @returns `none` when it names neither value, `invalid` when it names them
 *   but they are not a project and a public key, otherwise the settings.
 */
export function parseConnectFragment(fragment: string): ConnectLink {
  const parts = fragment.replace(/^#/, '').split('&').filter(isOwnPart);
  if (parts.length === 0) return { kind: 'none' };
  const values = new Map(parts.map((part) => decodedPair(part) ?? ['', '']));
  const ref = values.get(CONNECT_PROJECT_PARAM)?.trim() ?? '';
  const key = values.get(CONNECT_KEY_PARAM)?.trim() ?? '';
  if (!PROJECT_REF.test(ref) || !isPublicKey(key)) return { kind: 'invalid' };
  return { kind: 'valid', settings: { url: projectAddress(ref), anonKey: key } };
}

/**
 * The fragment without the link's own two values. Everything else is left as
 * it was, character for character: after a sign-in, Supabase puts its own
 * values there too.
 */
export function withoutConnectValues(fragment: string): string {
  return fragment
    .replace(/^#/, '')
    .split('&')
    .filter((part) => part !== '' && !isOwnPart(part))
    .join('&');
}

/**
 * Reads a link the owner pasted: the whole link, or only the part after `#`.
 *
 * @returns The settings, or null when it is not a usable personal link.
 */
export function parsePastedLink(text: string): SupabaseSettings | null {
  const trimmed = text.trim();
  const hash = trimmed.indexOf('#');
  const link = parseConnectFragment(hash >= 0 ? trimmed.slice(hash + 1) : trimmed);
  return link.kind === 'valid' ? link.settings : null;
}
