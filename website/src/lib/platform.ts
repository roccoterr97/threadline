/** The kinds of computer the set-up runs on. */
export type Platform = 'mac' | 'windows' | 'linux';

export const PLATFORMS: readonly Platform[] = ['mac', 'windows', 'linux'];

export const PLATFORM_LABELS: Record<Platform, string> = {
  mac: 'Mac',
  windows: 'Windows',
  linux: 'Linux',
};

/** A best guess from the browser, so the right install line shows first. */
export function detectPlatform(userAgent: string): Platform {
  if (/windows/i.test(userAgent)) return 'windows';
  if (/linux|x11|cros/i.test(userAgent) && !/android/i.test(userAgent)) return 'linux';
  return 'mac';
}

export function isPlatform(value: unknown): value is Platform {
  return typeof value === 'string' && (PLATFORMS as readonly string[]).includes(value);
}
