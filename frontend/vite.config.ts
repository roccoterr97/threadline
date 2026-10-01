/// <reference types="vitest/config" />
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

/** What search engines show for the public demo. */
const DEMO_DESCRIPTION =
  'Threadline demo: every conversation, one clear line. A self-hosted tracker that reads your mailbox and LinkedIn and tells you who is waiting for whom. Made-up data.';

/**
 * Only the public demo may be listed by search engines. A real dashboard keeps
 * its "do not list" tag; the demo build swaps it for a public description.
 */
function demoListing(isDemo: boolean): Plugin {
  return {
    name: 'threadline-demo-listing',
    transformIndexHtml(html) {
      if (!isDemo) return html;
      return html
        .replace(/\s*<meta name="robots" content="noindex, nofollow" \/>/, '')
        .replace(
          '<meta name="description" content="Private Threadline dashboard." />',
          `<meta name="description" content="${DEMO_DESCRIPTION}" />`,
        );
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), demoListing(demoFlag(mode) === 'true')],
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
    },
  },
}));
