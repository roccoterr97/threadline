import { afterEach, describe, expect, it } from 'vitest';
import { sectionAtLine } from './useActiveSection';

const IDS = ['first', 'second', 'third'];

/** Puts three sections on the page with their tops at the given distances from the screen's top edge. */
function placeSections(tops: readonly number[]) {
  IDS.forEach((id, index) => {
    const element = document.createElement('div');
    element.id = id;
    element.getBoundingClientRect = () => ({ top: tops[index] ?? 0 }) as DOMRect;
    document.body.append(element);
  });
}

afterEach(() => {
  document.body.replaceChildren();
});

describe('which section is being read', () => {
  it('is none while the first section is still below the line', () => {
    placeSections([400, 600, 800]);
    expect(sectionAtLine(IDS, 100, false)).toBeNull();
  });

  it('is the last one whose top has passed the line', () => {
    placeSections([-300, 24, 160]);
    expect(sectionAtLine(IDS, 100, false)).toBe('second');
  });

  it('is the last one at the very bottom of the page, even if it never reached the line', () => {
    placeSections([-300, -100, 500]);
    expect(sectionAtLine(IDS, 100, true)).toBe('third');
  });

  it('skips sections that are not on the page', () => {
    placeSections([-300, 24, 160]);
    expect(sectionAtLine(['missing', ...IDS], 100, false)).toBe('second');
  });
});
