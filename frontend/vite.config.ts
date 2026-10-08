/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

/** `vite --mode demo` (what `npm run demo` runs) turns the demo on. */
const DEMO_MODE = 'demo';

/**
 * The demo is on for the demo mode or when `VITE_DEMO=true` is set. The flag
 * is always written into the code as a fixed value, so a normal build can
 * drop the demo branch and its code entirely.
 */
function demoFlag(mode: string): 'true' | 'false' {
  const env = loadEnv(mode, import.meta.dirname, 'VITE_');
  return mode === DEMO_MODE || env.VITE_DEMO === 'true' ? 'true' : 'false';
}

/** What search engines and link previews show for the public demo. */
const DEMO_TITLE = 'Threadline demo';
const DEMO_DESCRIPTION =
  'Threadline demo: every conversation, one clear line. A self-hosted tracker that reads your mailbox and LinkedIn and tells you who is waiting for whom. Made-up data.';
const DEMO_IMAGE_ALT = 'The Threadline tick beside a list of people, each with a status chip.';

/** The link-preview picture (made by `npm run social-card`) and the name it is published under. */
const SOCIAL_CARD_SOURCE = new URL('./assets/social-card.png', import.meta.url);
const SOCIAL_CARD_FILE = 'social-card.png';
const SOCIAL_CARD_SIZE = { width: 1200, height: 630 } as const;

/**
 * The demo's public address, for link previews, which need full addresses.
 * `DEMO_SITE_URL` wins; on Vercel the project's production address is used.
 * Null when neither is set: the preview tags then use a path alone.
 */
function demoSiteUrl(mode: string): string | null {
  const env = loadEnv(mode, import.meta.dirname, '');
  const raw = env.DEMO_SITE_URL || env.VERCEL_PROJECT_PRODUCTION_URL || '';
  if (raw === '') return null;
  return new URL(/^https?:\/\//.test(raw) ? raw : `https://${raw}`).origin;
}

/** Text made safe to sit inside a double-quoted HTML attribute. */
function attribute(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/** The Open Graph and X (Twitter) tags that make a shared demo link show a card. */
function previewTags(siteUrl: string | null): string {
  const image = `${siteUrl ?? ''}/${SOCIAL_CARD_FILE}`;
  const tags: Array<[string, string, string]> = [
    ['property', 'og:type', 'website'],
    ['property', 'og:site_name', 'Threadline'],
    ['property', 'og:title', DEMO_TITLE],
    ['property', 'og:description', DEMO_DESCRIPTION],
    ['property', 'og:image', image],
    ['property', 'og:image:width', String(SOCIAL_CARD_SIZE.width)],
    ['property', 'og:image:height', String(SOCIAL_CARD_SIZE.height)],
    ['property', 'og:image:alt', DEMO_IMAGE_ALT],
    ['name', 'twitter:card', 'summary_large_image'],
    ['name', 'twitter:title', DEMO_TITLE],
    ['name', 'twitter:description', DEMO_DESCRIPTION],
    ['name', 'twitter:image', image],
    ['name', 'twitter:image:alt', DEMO_IMAGE_ALT],
  ];
  if (siteUrl !== null) tags.push(['property', 'og:url', `${siteUrl}/`]);
  return tags
    .map(([kind, key, value]) => `<meta ${kind}="${key}" content="${attribute(value)}" />`)
    .join('\n    ');
}

/**
 * Only the public demo may be listed by search engines or show a link
 * preview. A real dashboard keeps its "do not list" tag and publishes no
 * picture; the demo build swaps the tag for a public description, adds the
 * preview tags and publishes the preview picture.
 */
function demoListing(isDemo: boolean, siteUrl: string | null): Plugin {
  return {
    name: 'threadline-demo-listing',
    transformIndexHtml(html) {
      if (!isDemo) return html;
      return html
        .replace(/\s*<meta name="robots" content="noindex, nofollow" \/>/, '')
        .replace(
          '<meta name="description" content="Private Threadline dashboard." />',
          `<meta name="description" content="${attribute(DEMO_DESCRIPTION)}" />\n    ${previewTags(siteUrl)}`,
        );
    },
    generateBundle() {
      if (!isDemo) return;
      this.emitFile({
        type: 'asset',
        fileName: SOCIAL_CARD_FILE,
        source: readFileSync(SOCIAL_CARD_SOURCE),
      });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    demoListing(demoFlag(mode) === 'true', demoSiteUrl(mode)),
  ],
  define: {
    'import.meta.env.VITE_DEMO': JSON.stringify(demoFlag(mode)),
  },
  build: {
    // Source maps would expose the full component tree of a private dashboard.
    sourcemap: false,
    rollupOptions: {
      output: {
        // Libraries change far less often than the dashboard, so keeping them
        // apart lets a phone reuse them between deploys.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          supabase: ['@supabase/supabase-js'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    restoreMocks: true,
    include: ['src/**/*.test.{ts,tsx}'],
    env: {
      // Stand-ins so `isConfigured()` is true in tests. Every test mocks the
      // data layer, so nothing ever reaches the network.
      VITE_SUPABASE_URL: 'http://supabase.test',
      VITE_SUPABASE_ANON_KEY: 'test-anon-key',
      // Day boundaries ("yesterday") depend on the browser's zone. Pinning one
      // zone makes those tests mean the same on any machine.
      TZ: 'Europe/Paris',
    },
  },
}));
