import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { hasFixedSettings } from '../lib/runtimeConfig';
import { forgetConnection, readSavedConnection, saveConnection } from '../lib/savedConnection';
import { installMemoryStorage } from '../test/memoryStorage';
import {
  decideLinkAction,
  restartOnNewLink,
  startConnection,
  takeConnectLink,
} from './connectionStartup';

vi.mock('../lib/runtimeConfig', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/runtimeConfig')>()),
  hasFixedSettings: vi.fn(() => false),
}));

const REF = 'abcdefghijklmnopqrst';
const LINKED = { url: `https://${REF}.supabase.co`, anonKey: 'sb_publishable_x' };
const OTHER = { url: 'https://zyxwvutsrqponmlkjihg.supabase.co', anonKey: 'sb_publishable_y' };
const LINK = { kind: 'valid', settings: LINKED } as const;

describe('decideLinkAction', () => {
  it('keeps things as they are without a link', () => {
    expect(decideLinkAction({ kind: 'none' }, OTHER, false)).toEqual({ kind: 'keep' });
  });

  it('ignores a link on a page whose database is fixed', () => {
    expect(decideLinkAction(LINK, null, true)).toEqual({ kind: 'keep' });
  });

  it('saves the first link', () => {
    expect(decideLinkAction(LINK, null, false)).toEqual({ kind: 'save', settings: LINKED });
  });

  it('saves a link to the same database, with its new key', () => {
    const before = { ...LINKED, anonKey: 'sb_publishable_old' };
    expect(decideLinkAction(LINK, before, false)).toEqual({ kind: 'save', settings: LINKED });
  });

  it('asks before switching to a different database', () => {
    expect(decideLinkAction(LINK, OTHER, false)).toEqual({
      kind: 'confirm',
      current: OTHER,
      incoming: LINKED,
    });
  });

  it('reports a link that is not complete', () => {
    expect(decideLinkAction({ kind: 'invalid' }, null, false)).toEqual({ kind: 'invalid' });
  });
});

describe('startConnection', () => {
  beforeEach(() => {
    installMemoryStorage();
    vi.mocked(hasFixedSettings).mockReturnValue(false);
  });

  afterEach(() => {
    forgetConnection();
    window.history.replaceState(null, '', '/');
  });

  it('reads, saves and removes the link, leaving the rest of the address', () => {
    window.history.replaceState(null, '', `/review?x=1#project=${REF}&key=sb_publishable_x&type=magiclink`);

    expect(startConnection()).toEqual({ kind: 'ready' });

    expect(readSavedConnection()).toEqual(LINKED);
    expect(`${window.location.pathname}${window.location.search}${window.location.hash}`).toBe(
      '/review?x=1#type=magiclink',
    );
  });

  it('leaves an address without a link untouched', () => {
    window.history.replaceState(null, '', '/#access_token=abc');

    expect(takeConnectLink()).toEqual({ kind: 'none' });
    expect(window.location.hash).toBe('#access_token=abc');
  });

  it('asks before replacing a saved database, and saves nothing yet', () => {
    saveConnection(OTHER);
    window.history.replaceState(null, '', `/#project=${REF}&key=sb_publishable_x`);

    expect(startConnection()).toEqual({ kind: 'confirm-switch', current: OTHER, incoming: LINKED });
    expect(readSavedConnection()).toEqual(OTHER);
    expect(window.location.hash).toBe('');
  });

  it('says so when the link is not complete, and removes it anyway', () => {
    window.history.replaceState(null, '', `/#project=${REF}`);

    expect(startConnection()).toEqual({ kind: 'invalid-link' });
    expect(window.location.hash).toBe('');
    expect(readSavedConnection()).toBeNull();
  });

  it('never saves a link on a dashboard with its own settings', () => {
    vi.mocked(hasFixedSettings).mockReturnValue(true);
    window.history.replaceState(null, '', `/#project=${REF}&key=sb_publishable_x`);

    expect(startConnection()).toEqual({ kind: 'ready' });
    expect(readSavedConnection()).toBeNull();
    expect(window.location.hash).toBe('');
  });
});

describe('restartOnNewLink', () => {
  it('starts the page again when a link arrives in an open tab, and only then', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, hash: '#type=magiclink', reload });
    restartOnNewLink();

    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(reload).not.toHaveBeenCalled();

    vi.stubGlobal('location', { ...window.location, hash: `#project=${REF}&key=sb_publishable_x`, reload });
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(reload).toHaveBeenCalledOnce();
  });
});
