import { vi } from 'vitest';

/**
 * A browser storage kept in memory. Newer Node.js versions put their own
 * `localStorage` in front of the browser stand-in's, and it does nothing
 * without a file, so tests that keep something install this one instead.
 */
class MemoryStorage implements Storage {
  private readonly items = new Map<string, string>();

  get length(): number {
    return this.items.size;
  }

  clear(): void {
    this.items.clear();
  }

  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.items.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.items.delete(key);
  }

  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
}

/** Gives the page an empty storage of its own, and returns it. */
export function installMemoryStorage(): Storage {
  const storage = new MemoryStorage();
  vi.stubGlobal('localStorage', storage);
  return storage;
}
