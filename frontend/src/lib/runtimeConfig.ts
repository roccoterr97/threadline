import { z } from 'zod';

/**
 * Where the dashboard finds its database.
 *
 * A dashboard published by `tracker setup dashboard` is one prebuilt bundle
 * shared by every owner, so it cannot carry anybody's project address. The
 * set-up adds a tiny `config.js` beside it instead, which `index.html` loads
 * before the bundle and which sets this global. A dashboard built on a
 * contributor's machine (`npm run dev` with `.env.local`) or on a host that
 * builds from the repository has the two `VITE_` values compiled in.
 */
export const RUNTIME_CONFIG_GLOBAL = '__THREADLINE_CONFIG__';

/** The two public values the dashboard needs: never the secret key. */
export interface SupabaseSettings {
  url: string;
  anonKey: string;
}

const address = z.string().trim().url();
const key = z.string().trim().min(1);

const publishedSchema = z.object({ supabaseUrl: address, supabaseAnonKey: key });
const compiledSchema = z.object({ VITE_SUPABASE_URL: address, VITE_SUPABASE_ANON_KEY: key });

/**
 * Picks the settings: the published `config.js` first, then the compiled-in
 * `VITE_` values. Each source counts only when both of its values are usable,
 * so a half-filled source never mixes with the other.
 *
 * @param published - Whatever `config.js` left in the global, if anything.
 * @param compiled - The build-time environment (`import.meta.env`).
 * @returns The settings, or `null` when neither source has both values.
 */
export function resolveSupabaseSettings(
  published: unknown,
  compiled: Record<string, unknown>,
): SupabaseSettings | null {
  const fromPage = publishedSchema.safeParse(published);
  if (fromPage.success) {
    return { url: fromPage.data.supabaseUrl, anonKey: fromPage.data.supabaseAnonKey };
  }
  const fromBuild = compiledSchema.safeParse(compiled);
  if (fromBuild.success) {
    return { url: fromBuild.data.VITE_SUPABASE_URL, anonKey: fromBuild.data.VITE_SUPABASE_ANON_KEY };
  }
  return null;
}

/** Reads the settings of this page: `config.js` first, then the build's `VITE_` values. */
export function readSupabaseSettings(): SupabaseSettings | null {
  const published: unknown = Reflect.get(globalThis, RUNTIME_CONFIG_GLOBAL);
  // Vite types every build-time setting as `any`; treat them as unknown values.
  const compiled: Record<string, unknown> = import.meta.env;
  return resolveSupabaseSettings(published, compiled);
}
