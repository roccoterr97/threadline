// @vitest-environment node
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  netlifyHeadersFile,
  netlifyRedirectsFile,
  SECURITY_HEADERS,
  SPA_FALLBACK,
  UNLISTED_HEADER,
} from './hostingRules';

interface VercelHeaderRule {
  source: string;
  missing?: unknown[];
  headers: Array<{ key: string; value: string }>;
}

interface VercelConfig {
  rewrites: Array<{ source: string; destination: string }>;
  headers: VercelHeaderRule[];
}

/**
 * The copies the set-up publishes: it never trusts the `_headers` and `_redirects`
 * inside the downloaded dashboard, so it writes its own from these two files.
 */
const SETUP_COPIES = '../../../backend/src/tracker/services/setup/netlify_site/';

function setupCopy(name: string): string {
  return readFileSync(new URL(`${SETUP_COPIES}${name}`, import.meta.url), 'utf8');
}

const vercel = JSON.parse(
  readFileSync(new URL('../../vercel.json', import.meta.url), 'utf8'),
) as VercelConfig;

function pairs(rule: VercelHeaderRule | undefined): Array<[string, string]> {
  return (rule?.headers ?? []).map(({ key, value }) => [key, value]);
}

describe('vercel.json', () => {
  it('sends exactly the shared security headers on every address', () => {
    const everywhere = vercel.headers.find((rule) => rule.missing === undefined);
    expect(pairs(everywhere)).toEqual(SECURITY_HEADERS.map(([name, value]) => [name, value]));
  });

  it('keeps every address but the demo unlisted', () => {
    const unlisted = vercel.headers.find((rule) => rule.missing !== undefined);
    expect(pairs(unlisted)).toEqual([[...UNLISTED_HEADER]]);
  });

  it('opens the dashboard for every address that is not a file', () => {
    expect(vercel.rewrites).toEqual([{ source: '/(.*)', destination: SPA_FALLBACK.to }]);
  });
});

describe("Netlify's files", () => {
  it('send the security headers and the unlisted header on every address', () => {
    const lines = netlifyHeadersFile().split('\n');
    expect(lines[0]).toBe('/*');
    for (const [name, value] of [...SECURITY_HEADERS, UNLISTED_HEADER]) {
      expect(lines).toContain(`  ${name}: ${value}`);
    }
  });

  it('let the browser talk to Supabase and load config.js, but run no inline script', () => {
    const policy = netlifyHeadersFile();
    expect(policy).toContain("connect-src 'self' https://*.supabase.co wss://*.supabase.co");
    expect(policy).toContain("script-src 'self';");
    expect(policy).not.toContain('unsafe-inline');
  });

  it('rewrite every other address to the dashboard', () => {
    expect(netlifyRedirectsFile()).toBe('/* /index.html 200\n');
  });
});

describe("the set-up's own copies of Netlify's files", () => {
  const update =
    'update backend/src/tracker/services/setup/netlify_site/ from hostingRules.ts';

  it(`_headers match what the build writes (${update})`, () => {
    expect(setupCopy('_headers')).toBe(netlifyHeadersFile());
  });

  it(`_redirects match what the build writes (${update})`, () => {
    expect(setupCopy('_redirects')).toBe(netlifyRedirectsFile());
  });
});
