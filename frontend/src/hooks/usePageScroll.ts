import { useEffect, useLayoutEffect, useRef } from 'react';
import { NavigationType, useLocation, useNavigationType } from 'react-router-dom';

/**
 * Where the page is scrolled on each new page, the way a site of separate
 * pages behaves.
 *
 * Opening another page starts it at the top: without this, a person opened
 * from far down the list on a phone showed up scrolled to the bottom. Going
 * back (or forward) puts the page where it was left. Changing the filters on
 * the same page leaves the scroll alone.
 */
export function usePageScroll(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const positions = useRef(new Map<string, number>());
  const shownPath = useRef(location.pathname);

  // Remember the position on every scroll, so it is known before the next page replaces this one.
  useEffect(() => {
    const key = location.key;
    const remember = () => {
      positions.current.set(key, window.scrollY);
    };
    window.addEventListener('scroll', remember, { passive: true });
    return () => {
      window.removeEventListener('scroll', remember);
    };
  }, [location.key]);

  useLayoutEffect(() => {
    if (shownPath.current === location.pathname) return;
    shownPath.current = location.pathname;
    const top =
      navigationType === NavigationType.Pop ? (positions.current.get(location.key) ?? 0) : 0;
    window.scrollTo(0, top);
  }, [location.key, location.pathname, navigationType]);
}
