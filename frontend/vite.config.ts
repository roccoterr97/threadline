/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
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

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
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
