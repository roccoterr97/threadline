/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        // The libraries change far less often than the pages, so keeping them
        // apart lets a browser reuse them between deploys.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
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
    poolOptions: {
      // Node 22+ ships its own `localStorage` global, which is empty without a
      // flag and hides jsdom's. The tests need jsdom's.
      forks: { execArgv: ['--no-experimental-webstorage'] },
    },
  },
});
