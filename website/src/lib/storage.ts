import type { ZodType, ZodTypeDef } from 'zod';

/**
 * The browser's local storage, read and written safely.
 *
 * Storage can be missing (a private window, blocked site data) or hold
 * rubbish from an older version, so every read goes through a schema and
 * every failure counts as "nothing stored".
 */

/** Reads one value, or `null` when it is missing, broken or storage is unavailable. */
export function readStored<T>(key: string, schema: ZodType<T, ZodTypeDef, unknown>): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    const parsed = schema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** Writes one value; a browser that refuses is treated as "not remembered". */
export function writeStored(key: string, value: unknown): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

/** Forgets one value. */
export function clearStored(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Nothing to forget when storage is unavailable.
  }
}
