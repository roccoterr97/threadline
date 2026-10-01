import { useEffect } from 'react';
import * as copy from '../copy/en';

/**
 * Names the browser tab after the page, such as "People – Threadline", so
 * tabs, history and screen readers can tell the pages apart.
 *
 * @param page The page's own name; null while it is not known yet (the app's
 *   name alone is shown meanwhile).
 */
export function usePageTitle(page: string | null): void {
  useEffect(() => {
    document.title = page === null ? copy.app.name : copy.app.pageTitle(page);
  }, [page]);
}
