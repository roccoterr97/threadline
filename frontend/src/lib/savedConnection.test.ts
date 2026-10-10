import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installMemoryStorage } from '../test/memoryStorage';
import {
  forgetConnection,
  readSavedConnection,
  SAVED_CONNECTION_KEY,
  saveConnection,
} from './savedConnection';

const SETTINGS = { url: 'https://abcdefghijklmnopqrst.supabase.co', anonKey: 'sb_publishable_x' };

let storage: Storage;

beforeEach(() => {
  storage = installMemoryStorage();
});

afterEach(() => {
  forgetConnection();
});

describe('savedConnection', () => {
  it('keeps the database for the next visit and forgets it on request', () => {
    expect(readSavedConnection()).toBeNull();
    expect(saveConnection(SETTINGS)).toBe(true);
    expect(JSON.parse(storage.getItem(SAVED_CONNECTION_KEY) ?? '')).toEqual(SETTINGS);
    expect(readSavedConnection()).toEqual(SETTINGS);

    forgetConnection();

    expect(readSavedConnection()).toBeNull();
  });

  it('ignores what something else wrote under its name', () => {
    storage.setItem(SAVED_CONNECTION_KEY, 'not json');
    expect(readSavedConnection()).toBeNull();
    storage.setItem(SAVED_CONNECTION_KEY, JSON.stringify({ url: 'nope', anonKey: 'k' }));
    expect(readSavedConnection()).toBeNull();
  });

  it('keeps the database in this tab when the browser refuses to store it', () => {
    vi.spyOn(storage, 'setItem').mockImplementation(() => {
      throw new DOMException('refused', 'SecurityError');
    });
    vi.spyOn(storage, 'getItem').mockImplementation(() => {
      throw new DOMException('refused', 'SecurityError');
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(saveConnection(SETTINGS)).toBe(false);
    expect(readSavedConnection()).toEqual(SETTINGS);
  });
});
