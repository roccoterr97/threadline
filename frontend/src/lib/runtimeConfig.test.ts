import { afterEach, describe, expect, it } from 'vitest';
import {
  readSupabaseSettings,
  readSupabaseSource,
  resolveSupabaseSettings,
  resolveSupabaseSource,
  RUNTIME_CONFIG_GLOBAL,
} from './runtimeConfig';
import { installMemoryStorage } from '../test/memoryStorage';
import { forgetConnection, saveConnection } from './savedConnection';

const PUBLISHED = {
  supabaseUrl: 'https://published.supabase.example',
  supabaseAnonKey: 'published-key',
};
const COMPILED = {
  VITE_SUPABASE_URL: 'https://compiled.supabase.example',
  VITE_SUPABASE_ANON_KEY: 'compiled-key',
};
const SAVED = { url: 'https://saved.supabase.example', anonKey: 'saved-key' };

describe('resolveSupabaseSettings', () => {
  it('prefers the values config.js published over the compiled ones', () => {
    expect(resolveSupabaseSettings(PUBLISHED, COMPILED)).toEqual({
      url: 'https://published.supabase.example',
      anonKey: 'published-key',
    });
  });

  it('falls back to the compiled values when the page published none', () => {
    expect(resolveSupabaseSettings(undefined, COMPILED)).toEqual({
      url: 'https://compiled.supabase.example',
      anonKey: 'compiled-key',
    });
  });

  it('never mixes a half-filled config.js with the compiled values', () => {
    const halfFilled = { supabaseUrl: PUBLISHED.supabaseUrl, supabaseAnonKey: '   ' };
    expect(resolveSupabaseSettings(halfFilled, COMPILED)?.url).toBe(COMPILED.VITE_SUPABASE_URL);
  });

  it.each([
    ['text', 'https://published.supabase.example'],
    ['null', null],
    ['an address that is not one', { ...PUBLISHED, supabaseUrl: 'not an address' }],
    ['a key that is not text', { ...PUBLISHED, supabaseAnonKey: 42 }],
  ])('ignores a config.js holding %s', (_label, published) => {
    expect(resolveSupabaseSettings(published, COMPILED)?.anonKey).toBe('compiled-key');
  });

  it('trims stray spaces around both values', () => {
    const spaced = { supabaseUrl: ' https://a.supabase.example ', supabaseAnonKey: ' key ' };
    expect(resolveSupabaseSettings(spaced, {})).toEqual({
      url: 'https://a.supabase.example',
      anonKey: 'key',
    });
  });

  it('is null when neither source has both values', () => {
    expect(resolveSupabaseSettings(undefined, {})).toBeNull();
    expect(resolveSupabaseSettings({}, { VITE_SUPABASE_URL: COMPILED.VITE_SUPABASE_URL })).toBeNull();
    expect(resolveSupabaseSettings(undefined, { ...COMPILED, VITE_SUPABASE_ANON_KEY: '' })).toBeNull();
  });
});

describe('resolveSupabaseSource', () => {
  it('ranks config.js first, the build second and a saved link last', () => {
    expect(resolveSupabaseSource(PUBLISHED, COMPILED, SAVED)?.source).toBe('config-file');
    expect(resolveSupabaseSource(undefined, COMPILED, SAVED)?.source).toBe('build');
    expect(resolveSupabaseSource(undefined, {}, SAVED)).toEqual({ settings: SAVED, source: 'saved-link' });
  });

  it('never mixes a half-filled source with a saved link', () => {
    const halfBuilt = { VITE_SUPABASE_URL: COMPILED.VITE_SUPABASE_URL };
    expect(resolveSupabaseSettings(undefined, halfBuilt, SAVED)).toEqual(SAVED);
    expect(resolveSupabaseSettings(undefined, {}, { url: SAVED.url, anonKey: '' })).toBeNull();
  });
});

describe('readSupabaseSettings', () => {
  // Set and removed by hand: unstubbing every global would also lift the
  // set-up's guard against network requests.
  afterEach(() => {
    Reflect.deleteProperty(globalThis, RUNTIME_CONFIG_GLOBAL);
    forgetConnection();
  });

  it('prefers the build values over a saved link', () => {
    installMemoryStorage();
    saveConnection(SAVED);
    expect(readSupabaseSource()?.source).toBe('build');
  });

  it('reads what config.js left on the page', () => {
    Reflect.set(globalThis, RUNTIME_CONFIG_GLOBAL, PUBLISHED);
    expect(readSupabaseSettings()?.url).toBe('https://published.supabase.example');
  });

  it('uses the build values without a config.js', () => {
    // The test set-up compiles in stand-in VITE_ values (see vite.config.ts).
    expect(readSupabaseSettings()?.url).toBe('http://supabase.test');
  });
});
