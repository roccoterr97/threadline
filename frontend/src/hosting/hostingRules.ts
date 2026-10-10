/**
 * The rules every host serves the dashboard with: its security headers and the
 * single-page fallback. They are written once, here.
 *
 * `vercel.json` cannot import code, so it repeats them, and a test fails when
 * the two drift apart. Netlify's `_headers` and `_redirects` files are made
 * from this module by the build (see `vite.config.ts`), so they cannot drift.
 */

/** One response header: its name and its value. */
export type Header = readonly [name: string, value: string];

/**
 * The browser may load code, styles, pictures and fonts from the dashboard's
 * own address only (`config.js` included), and talk to Supabase and nothing
 * else. Nothing may frame the page.
 */
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "manifest-src 'self'",
  "connect-src 'self' https://*.supabase.co wss://*.supabase.co",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

/** Headers sent with every page and file of the dashboard. */
export const SECURITY_HEADERS: readonly Header[] = [
  ['Content-Security-Policy', CONTENT_SECURITY_POLICY],
  ['Strict-Transport-Security', 'max-age=63072000; includeSubDomains'],
  ['X-Content-Type-Options', 'nosniff'],
  ['X-Frame-Options', 'DENY'],
  ['Referrer-Policy', 'no-referrer'],
];

/**
 * Asks search engines to leave the page out. A private dashboard always sends
 * it; on Vercel only the public demo's address goes without it.
 */
export const UNLISTED_HEADER: Header = ['X-Robots-Tag', 'noindex, nofollow'];

/** Every address that is not a file opens the dashboard, which routes it itself. */
export const SPA_FALLBACK = { from: '/*', to: '/index.html', status: 200 } as const;

/**
 * Vercel's answer to `/config.js`, which `index.html` always asks for. The
 * shared dashboard has no such file, and the fallback would answer with
 * `index.html`, a page the browser refuses to run as a script. A published
 * dashboard's own `config.js` is a real file, which every host serves before
 * any rule, so this never hides it.
 */
export const NO_CONFIG_REWRITE = { source: '/config.js', destination: '/no-config.js' } as const;

/** Vercel's rewrites, in order: the harmless `config.js`, then the fallback. */
export const VERCEL_REWRITES = [
  NO_CONFIG_REWRITE,
  { source: '/(.*)', destination: SPA_FALLBACK.to },
] as const;

/** Netlify's `_headers` file: every header above, for every address. */
export function netlifyHeadersFile(): string {
  const lines = [...SECURITY_HEADERS, UNLISTED_HEADER].map(([name, value]) => `  ${name}: ${value}`);
  return ['/*', ...lines, ''].join('\n');
}

/**
 * Netlify's `_redirects` file. Netlify serves a file that exists before it
 * applies a rule without `!`, so `config.js` and the assets are never rewritten.
 */
export function netlifyRedirectsFile(): string {
  return `${SPA_FALLBACK.from} ${SPA_FALLBACK.to} ${SPA_FALLBACK.status}\n`;
}
