import { useEffect } from 'react';

const SITE_NAME = 'Threadline';

/** Names the browser tab after the page, and restores the site's name on leaving. */
export function usePageTitle(title: string | null): void {
  useEffect(() => {
    document.title = title === null ? SITE_NAME : `${title} – ${SITE_NAME}`;
    return () => {
      document.title = SITE_NAME;
    };
  }, [title]);
}
