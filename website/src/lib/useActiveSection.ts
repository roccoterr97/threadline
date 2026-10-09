import { useEffect, useState } from 'react';

/**
 * How far down the screen, as a share of its height, a section's top must
 * have passed to count as the one being read. Kept small so that after a
 * jump to a section (it lands just below the top edge) that section is the
 * one marked, not the short one after it.
 */
const READING_LINE = 0.12;
/** Within this many pixels of the bottom, the last section counts: it may be too short to reach the line. */
const BOTTOM_SLACK = 2;

/** The last section, in page order, whose top has passed the reading line; or the last one at the very bottom. */
export function sectionAtLine(ids: readonly string[], line: number, atBottom: boolean): string | null {
  const present = ids.filter((id) => document.getElementById(id) !== null);
  if (atBottom && present.length > 0) return present[present.length - 1] ?? null;
  let current: string | null = null;
  for (const id of present) {
    const top = document.getElementById(id)?.getBoundingClientRect().top ?? Infinity;
    if (top > line) break;
    current = id;
  }
  return current;
}

function isAtBottom(): boolean {
  const page = document.documentElement;
  return window.scrollY > 0 && window.innerHeight + window.scrollY >= page.scrollHeight - BOTTOM_SLACK;
}

/** Which of the given sections is being read, so the margin's list can mark it. */
export function useActiveSection(ids: readonly string[]): string | null {
  const [active, setActive] = useState<string | null>(null);
  const key = ids.join('|');

  useEffect(() => {
    const order = key.split('|');
    let frame = 0;
    const update = () => {
      frame = 0;
      setActive(sectionAtLine(order, window.innerHeight * READING_LINE, isAtBottom()));
    };
    // At most one measurement per frame, however fast the page scrolls.
    const schedule = () => {
      if (frame === 0) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
    };
  }, [key]);

  return active;
}
