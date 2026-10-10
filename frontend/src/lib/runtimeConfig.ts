import { z } from 'zod';
import { readSavedConnection } from './savedConnection';

/**
 * Where the dashboard finds its database.
 *
 * A dashboard published by `tracker setup dashboard` is one prebuilt bundle
 * shared by every owner, so it cannot carry anybody's project address. The
 * set-up adds a tiny `config.js` beside it instead, which `index.html` loads
 * before the bundle and which sets this global. A dashboard built on a
 * contributor's machine (`npm run dev` with `.env.local`) or on a host that
 * builds from the repository has the two `VITE_` values compiled in. The
 * shared dashboard has neither: it uses the database an owner's personal link
 * connected this browser to (`connectLink.ts`, `savedConnection.ts`).
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

/** Where the settings came from, most fixed first. */
export type SettingsSource = 'config-file' | 'build' | 'saved-link';

/** The settings in use and where they came from. */
export interface ResolvedSettings {
  settings: SupabaseSettings;
  source: SettingsSource;
}

const savedSchema = z.object({ url: address, anonKey: key });

/**
 * Picks the settings: the published `config.js` first, then the compiled-in
 * `VITE_` values, then the database a personal link saved. Each source counts
 * only when both of its values are usable, so a half-filled source never mixes
 * with another.
 *
 * @param published - Whatever `config.js` left in the global, if anything.
 * @param compiled - The build-time environment (`import.meta.env`).
 * @param saved - What a personal link saved in this browser, if anything.
 * @returns The settings and their source, or `null` when no source has both values.
 */
export function resolveSupabaseSource(
  published: unknown,
  compiled: Record<string, unknown>,
  saved: unknown = null,
): ResolvedSettings | null {
  const fromPage = publishedSchema.safeParse(published);
  if (fromPage.success) {
    const { supabaseUrl, supabaseAnonKey } = fromPage.data;
    return { settings: { url: supabaseUrl, anonKey: supabaseAnonKey }, source: 'config-file' };
  }
  const fromBuild = compiledSchema.safeParse(compiled);
  if (fromBuild.success) {
    const { VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY } = fromBuild.data;
    return { settings: { url: VITE_SUPABASE_URL, anonKey: VITE_SUPABASE_ANON_KEY }, source: 'build' };
  }
  const fromLink = savedSchema.safeParse(saved);
  if (fromLink.success) return { settings: fromLink.data, source: 'saved-link' };
  return null;
}

/** The settings alone; see `resolveSupabaseSource`. */
export function resolveSupabaseSettings(
  published: unknown,
  compiled: Record<string, unknown>,
  saved: unknown = null,
): SupabaseSettings | null {
  return resolveSupabaseSource(published, compiled, saved)?.settings ?? null;
}

/** True when this page has a fixed database (`config.js` or the build) that no link may change. */
export function hasFixedSettings(): boolean {
  return resolveSupabaseSource(publishedValues(), compiledValues()) !== null;
}

/** Reads this page's settings and their source: `config.js`, the build, then a saved link. */
export function readSupabaseSource(): ResolvedSettings | null {
  return resolveSupabaseSource(publishedValues(), compiledValues(), readSavedConnection());
}

/** Reads the settings of this page; see `readSupabaseSource`. */
export function readSupabaseSettings(): SupabaseSettings | null {
  return readSupabaseSource()?.settings ?? null;
}

function publishedValues(): unknown {
  return Reflect.get(globalThis, RUNTIME_CONFIG_GLOBAL);
}

function compiledValues(): Record<string, unknown> {
  // Vite types every build-time setting as `any`; treat them as unknown values.
  return import.meta.env;
}
