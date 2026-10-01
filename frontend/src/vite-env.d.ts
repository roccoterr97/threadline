/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `'true'` in a demo build (`npm run demo`), `'false'` otherwise. Set in `vite.config.ts`. */
  readonly VITE_DEMO: 'true' | 'false';
}
