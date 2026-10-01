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

// jsdom implements none of these: the save banner uses the first two to bring
// itself on screen, and the layout scrolls each new page to the top. `restoreMocks` resets spies between tests, so they are put
// back before each one rather than once. A test file that runs outside the
// browser stand-in (the build check) has no `Element` and needs neither.
beforeEach(() => {
  if (typeof Element === 'undefined') return;
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('scrollTo', vi.fn());
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: false, media: query })),
  );
});
