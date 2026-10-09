import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// Nothing in the suite may reach the network. If a test ever tries, it fails
// here with a clear message instead of hanging or hitting a real service.
vi.stubGlobal(
  'fetch',
  vi.fn(() => {
    throw new Error('Tests must not make network requests');
  }),
);

// jsdom implements none of these: the pages scroll to the top on navigation
// and the copy buttons use the clipboard. `restoreMocks` resets spies between
// tests, so they are put back before each one rather than once.
beforeEach(() => {
  if (typeof Element === 'undefined') return;
  window.localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('scrollTo', vi.fn());
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: false, media: query })),
  );
});
