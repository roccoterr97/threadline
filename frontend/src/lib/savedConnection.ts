import { z } from 'zod';
import { logError } from './logger';
import type { SupabaseSettings } from './runtimeConfig';

/**
 * The database a personal link connected this browser to, kept so the shared
 * dashboard opens it again without the link. Only the two public values are
 * kept. Storage can be missing or refused (a private window, blocked site
 * data): then the database is kept in this tab only, and the owner opens the
 * link again next time.
 */

export const SAVED_CONNECTION_KEY = 'threadline.connection';

/** The tab's own copy, for when the browser refuses to keep anything. */
let keptInThisTab: SupabaseSettings | null = null;

const savedSchema = z.object({ url: z.string().url(), anonKey: z.string().min(1) });

/** What was saved before, or null when nothing usable was. */
export function readSavedConnection(): SupabaseSettings | null {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(SAVED_CONNECTION_KEY);
  } catch {
    logError('connection.read_refused');
    return keptInThisTab;
  }
  if (raw === null) return keptInThisTab;
  try {
    const parsed = savedSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    // Not JSON: something else wrote it. It is ignored, not trusted.
    logError('connection.unreadable');
    return null;
  }
}

/**
 * Keeps the database for the next visit (for this tab at least).
 *
 * @returns Whether the browser kept it for the next visit too.
 */
export function saveConnection(settings: SupabaseSettings): boolean {
  keptInThisTab = { url: settings.url, anonKey: settings.anonKey };
  try {
    window.localStorage.setItem(
      SAVED_CONNECTION_KEY,
      JSON.stringify({ url: settings.url, anonKey: settings.anonKey }),
    );
    return true;
  } catch {
    logError('connection.save_refused');
    return false;
  }
}

/** Forgets the database, so the next visit asks for a personal link again. */
export function forgetConnection(): void {
  keptInThisTab = null;
  try {
    window.localStorage.removeItem(SAVED_CONNECTION_KEY);
  } catch {
    logError('connection.forget_refused');
  }
}
