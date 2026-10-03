import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { NavigationType, useLocation, useNavigationType } from 'react-router-dom';
import { SCROLL_RESTORE_WAIT_MS } from '../constants/dashboard';
import {
  loadScrollPositions,
  recordScrollPosition,
  saveScrollPositions,
} from '../lib/scrollPositions';

/** Signs that the owner is moving the page themselves, so a waiting scroll gives way. */
const OWNER_SCROLL_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;

/** Ways of opening the page that come back to a place in the tab's history, not a new visit. */
const RETURNING_ARRIVALS: ReadonlySet<unknown> = new Set<NavigationTimingType>([
  'reload',
  'back_forward',
]);

/** The page on screen: its history entry and where it lives. */
interface ShownPage {
  key: string;
  pathname: string;
}

/**
 * The name a page's place is kept under. An entry the router did not make
 * itself (a typed address, a bookmark, the skip link's jump) has the key
 * "default", so the path keeps two such pages apart.
 */
function placeName({ key, pathname }: ShownPage): string {
  return `${key}:${pathname}`;
}

/** Whether this document was opened by a reload or by Back/Forward, rather than afresh. */
function openedByReturning(): boolean {
  const [arrival] = performance.getEntriesByType('navigation');
  return arrival !== undefined && 'type' in arrival && RETURNING_ARRIVALS.has(arrival.type);
}

/**
 * Scrolls to `top`. While the page is still too short to get there (its list
 * may still be loading), it tries again each time the page grows, until it
 * arrives, the owner scrolls, or the wait runs out. Each try goes as far as
 * the page allows, so a page that is now shorter than before (someone was
 * hidden, a banner went) still ends as close to the place as it can get.
 * Returns what stops it.
 */
function scrollToWhenShown(top: number): () => void {
  const tallEnough = () => document.documentElement.scrollHeight - window.innerHeight >= top;
  window.scrollTo(0, top);
  if (top <= 0 || tallEnough()) return () => undefined;

  const growth = new ResizeObserver(() => {
    window.scrollTo(0, top);
    if (tallEnough()) stop();
  });
  const timer = window.setTimeout(stop, SCROLL_RESTORE_WAIT_MS);
  function stop() {
    growth.disconnect();
    window.clearTimeout(timer);
    for (const type of OWNER_SCROLL_EVENTS) window.removeEventListener(type, stop);
  }
  growth.observe(document.body);
  for (const type of OWNER_SCROLL_EVENTS) window.addEventListener(type, stop, { passive: true });
  return stop;
}

/**
 * Switches off the browser's own restoring while mounted: it runs before the
 * page it belongs to is drawn, so it lands short on a longer page.
 */
function useOwnScrollRestoring(): void {
  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = 'manual';
    return () => {
      window.history.scrollRestoration = previous;
    };
  }, []);
}

/**
 * Where the page is scrolled on each new page, the way a site of separate
 * pages behaves.
 *
 * Opening another page starts it at the top: without this, a person opened
 * from far down the list on a phone showed up scrolled to the bottom. Going
 * back (or forward) puts the page where it was left, also after a reload.
 * A reload itself puts the page back too, as browsers do; an address opened
 * afresh starts at the top and forgets any place kept for it earlier.
 * Changing the filters on the same page leaves the scroll alone.
 */
export function usePageScroll(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const [positions] = useState(loadScrollPositions);
  // The page on screen. Updated in the same step that scrolls, so a scroll the
  // switch itself causes is never written down for the page just left.
  const shown = useRef<ShownPage>({ key: location.key, pathname: location.pathname });
  // Stops the wait for a page still too short to reach its place. Only the
  // next page stops it early: React also clears this hook's effects while
  // part of the page waits for its code, then runs them again, and that must
  // not cut the wait short. Otherwise it ends by itself (see scrollToWhenShown).
  const stopWaiting = useRef<() => void>(() => undefined);
  const arrived = useRef(false);
  useOwnScrollRestoring();

  useLayoutEffect(() => {
    if (arrived.current) return;
    arrived.current = true;
    const place = placeName(shown.current);
    if (openedByReturning()) {
      stopWaiting.current = scrollToWhenShown(positions.get(place) ?? 0);
      return;
    }
    positions.delete(place);
  }, [positions]);

  useEffect(() => {
    const remember = () => {
      recordScrollPosition(positions, placeName(shown.current), window.scrollY);
    };
    const keep = () => {
      saveScrollPositions(positions);
    };
    // A phone can throw away a tab in the background without a "pagehide",
    // so the places are also kept each time the page goes out of sight.
    const keepWhenHidden = () => {
      if (document.visibilityState === 'hidden') keep();
    };
    window.addEventListener('scroll', remember, { passive: true });
    window.addEventListener('pagehide', keep);
    document.addEventListener('visibilitychange', keepWhenHidden);
    return () => {
      window.removeEventListener('scroll', remember);
      window.removeEventListener('pagehide', keep);
      document.removeEventListener('visibilitychange', keepWhenHidden);
    };
  }, [positions]);

  useLayoutEffect(() => {
    const before = shown.current;
    const now = { key: location.key, pathname: location.pathname };
    if (placeName(before) === placeName(now)) return;
    shown.current = now;
    stopWaiting.current();
    stopWaiting.current = () => undefined;
    if (before.pathname === now.pathname) {
      // Same page, other filters: nothing moves, and Back must find this place too.
      recordScrollPosition(positions, placeName(now), window.scrollY);
      return;
    }
    const top = navigationType === NavigationType.Pop ? (positions.get(placeName(now)) ?? 0) : 0;
    stopWaiting.current = scrollToWhenShown(top);
  }, [location.key, location.pathname, navigationType, positions]);
}
