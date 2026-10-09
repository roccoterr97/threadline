import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { NotConfiguredError } from './errors';
import { readSupabaseSettings, type SupabaseSettings } from './runtimeConfig';

/**
 * The single Supabase client for the whole dashboard.
 *
 * Only the public ("anon") key is used here. It is designed to be readable by
 * anyone who opens the page; the database access rules are what keep the data
 * private, by refusing every table to anyone who is not the registered owner.
 * The service-role key must never appear anywhere under `frontend/`.
 */

let client: SupabaseClient | null = null;

/** The database settings, or a typed error saying they are missing. */
function requireSettings(): SupabaseSettings {
  const settings = readSupabaseSettings();
  if (settings === null) {
    throw new NotConfiguredError('Missing the database address or public key');
  }
  return settings;
}

/**
 * True when there is something to talk to — both settings are present (see
 * `runtimeConfig.ts`), or a client was installed at start-up — so the UI can
 * explain rather than crash.
 */
export function isConfigured(): boolean {
  return client !== null || readSupabaseSettings() !== null;
}

/**
 * Returns the shared client, creating it on first use.
 *
 * @throws {NotConfiguredError} when the page has no database settings.
 */
export function getSupabaseClient(): SupabaseClient {
  if (client === null) {
    const { url, anonKey } = requireSettings();
    client = createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: 'pkce',
      },
    });
  }
  return client;
}

/**
 * Uses `replacement` for the rest of the session instead of a real client.
 * Called once, before the first render, by the demo — and never otherwise.
 */
export function installSupabaseClient(replacement: SupabaseClient): void {
  client = replacement;
}
