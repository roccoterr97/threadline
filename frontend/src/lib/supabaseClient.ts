import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { NotConfiguredError } from './errors';

/**
 * The single Supabase client for the whole dashboard.
 *
 * Only the public ("anon") key is used here. It is designed to be readable by
 * anyone who opens the page; the database access rules are what keep the data
 * private, by refusing every table to anyone who is not the registered owner.
 * The service-role key must never appear anywhere under `frontend/`.
 */

let client: SupabaseClient | null = null;

function readSetting(name: 'VITE_SUPABASE_URL' | 'VITE_SUPABASE_ANON_KEY'): string {
  // Vite types every build-time setting as `any`; treat them as unknown text.
  const settings: Record<string, unknown> = import.meta.env;
  const value = settings[name];
  if (typeof value !== 'string' || value.trim() === '') {
    throw new NotConfiguredError(`Missing ${name}`);
  }
  return value.trim();
}

/**
 * True when there is something to talk to — both settings are present, or a
 * client was installed at start-up — so the UI can explain rather than crash.
 */
export function isConfigured(): boolean {
  if (client !== null) return true;
  try {
    readSetting('VITE_SUPABASE_URL');
    readSetting('VITE_SUPABASE_ANON_KEY');
    return true;
  } catch (error) {
    if (error instanceof NotConfiguredError) return false;
    throw error;
  }
}

/**
 * Returns the shared client, creating it on first use.
 *
 * @throws {NotConfiguredError} when the two `VITE_` settings are not set.
 */
export function getSupabaseClient(): SupabaseClient {
  if (client === null) {
    client = createClient(readSetting('VITE_SUPABASE_URL'), readSetting('VITE_SUPABASE_ANON_KEY'), {
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
