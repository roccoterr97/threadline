import { Suspense, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import * as copy from '../copy/en';
import { SiteFooter } from './SiteFooter';
import { SiteHeader } from './SiteHeader';

const MAIN_ID = 'main';

/** Holds the page's place while its code arrives, so the header and footer never blink away. */
function PageLoading() {
  return (
    <div className="min-h-[60vh]">
      <p role="status" className="sr-only">
        {copy.site.loading}
      </p>
    </div>
  );
}

/** The frame of every page: skip link, header, the page, footer. */
export function SiteLayout() {
  const { pathname, hash } = useLocation();

  // A new page starts at the top, unless the address names a section.
  useEffect(() => {
    if (hash !== '') {
      document.getElementById(hash.slice(1))?.scrollIntoView();
      return;
    }
    window.scrollTo(0, 0);
  }, [pathname, hash]);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded-token-sm focus:bg-surface focus:px-3 focus:py-2"
      >
        {copy.site.skipToContent}
      </a>
      <SiteHeader />
      <main id={MAIN_ID} className="flex-1">
        <Suspense fallback={<PageLoading />}>
          {/* Keyed by address so each new page settles in once. */}
          <div key={pathname} className="page-enter">
            <Outlet />
          </div>
        </Suspense>
      </main>
      <SiteFooter />
    </div>
  );
}
