import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SCROLL_PLACES_KEPT } from '../constants/dashboard';
import { loadScrollPositions, recordScrollPosition, saveScrollPositions } from './scrollPositions';

const STORAGE_KEY = 'threadline.scroll-positions';

beforeEach(() => {
  window.sessionStorage.clear();
});

describe('the scroll positions kept for the tab', () => {
  it('reads back what was kept, as entry keys and offsets only', () => {
    saveScrollPositions(new Map([['a1b2c3', 1800]]));

    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe('{"a1b2c3":1800}');
    expect(loadScrollPositions()).toEqual(new Map([['a1b2c3', 1800]]));
  });

  it('lets the oldest place go once it keeps as many as it may', () => {
    const positions = new Map<string, number>();
    for (let page = 0; page <= SCROLL_PLACES_KEPT; page += 1) {
      recordScrollPosition(positions, `page-${page}`, page);
    }

    expect(positions.size).toBe(SCROLL_PLACES_KEPT);
    expect(positions.has('page-0')).toBe(false);
    expect(positions.get(`page-${SCROLL_PLACES_KEPT}`)).toBe(SCROLL_PLACES_KEPT);
  });

  it('counts a place written down again as the newest', () => {
    const positions = new Map([['first', 10], ['second', 20]]);
    recordScrollPosition(positions, 'first', 30);

    expect([...positions.keys()]).toEqual(['second', 'first']);
  });

  it('reads back no more than it may keep, the newest ones', () => {
    const stored = Object.fromEntries(
      Array.from({ length: SCROLL_PLACES_KEPT + 5 }, (_, page) => [`page-${page}`, page]),
    );
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored));

    const positions = loadScrollPositions();
    expect(positions.size).toBe(SCROLL_PLACES_KEPT);
    expect(positions.has('page-4')).toBe(false);
    expect(positions.has('page-5')).toBe(true);
  });

  it('starts empty when nothing was kept', () => {
    expect(loadScrollPositions()).toEqual(new Map());
  });

  it.each(['not json', '["a1b2c3"]', '{"a1b2c3":"far"}'])(
    'ignores a kept value it does not recognise (%s)',
    (stored) => {
      vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      window.sessionStorage.setItem(STORAGE_KEY, stored);
      expect(loadScrollPositions()).toEqual(new Map());
    },
  );

  it('carries on from memory when the browser keeps no storage', () => {
    const refusal = new DOMException('Storage is switched off.', 'SecurityError');
    // Browsers with site data blocked refuse as soon as the storage is touched.
    vi.spyOn(window, 'sessionStorage', 'get').mockImplementation(() => {
      throw refusal;
    });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    expect(loadScrollPositions()).toEqual(new Map());
    expect(() => {
      saveScrollPositions(new Map([['a1b2c3', 1800]]));
    }).not.toThrow();
    expect(warn).toHaveBeenCalledWith(
      expect.objectContaining({ event: 'scroll_positions.not_saved', reason: 'SecurityError' }),
    );
  });
});
