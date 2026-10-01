import { useQuery } from '@tanstack/react-query';
import { Link, Outlet } from 'react-router-dom';
import { fetchOpenReviewItems, reviewQueryKey } from '../api/review';
import { useAuth } from '../auth/useAuth';
import * as copy from '../copy/en';
import { useRefreshNow } from '../hooks/useRefreshNow';
import { BottomNav } from './BottomNav';
import { Button } from './Button';
import { HeaderNav } from './HeaderNav';
import { Icon } from './Icon';
import { Logo } from './Logo';
import { RefreshButton } from './RefreshButton';
import { RefreshStatus } from './RefreshStatus';

const MAIN_ID = 'main-content';
const REFRESH_STATUS_ID = 'refresh-status';

/**
 * The frame every signed-in screen sits inside: header, navigation, content.
 *
 * From tablet width up the menu sits in the header. On a phone the header
 * keeps only the name, "Refresh" and "Sign out", the menu moves to a bar at the bottom,
 * and the content gets extra room below so nothing hides behind that bar.
 * What "Refresh now" is doing shows on one line under the header.
 */
export function AppLayout() {
  const { signOut } = useAuth();
  const openReview = useQuery({
    queryKey: reviewQueryKey,
    queryFn: fetchOpenReviewItems,
  });
  const openCount = openReview.data?.length ?? 0;
  const refresh = useRefreshNow();

  return (
    <div className="min-h-dvh bg-bg">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded-token-md focus:bg-surface focus:px-3 focus:py-2 focus:text-ink"
      >
        {copy.app.skipToContent}
      </a>

      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link
            to="/"
            className="flex min-h-11 min-w-0 items-center gap-2 rounded-token-md text-base font-semibold text-ink"
          >
            <Logo />
            {/* The narrowest phones keep only the logo; the name is still read out. */}
            <span className="truncate max-[399px]:sr-only">{copy.app.name}</span>
          </Link>
          <HeaderNav reviewCount={openCount} />
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <RefreshButton
              status={refresh.status}
              statusId={REFRESH_STATUS_ID}
              onStart={refresh.start}
            />
            <Button
              variant="secondary"
              className="shrink-0"
              onClick={() => {
                void signOut();
              }}
            >
              <Icon name="signOut" className="h-4 w-4" />
              {copy.nav.signOut}
            </Button>
          </div>
        </div>
        <RefreshStatus id={REFRESH_STATUS_ID} status={refresh.status} />
      </header>

      <main
        id={MAIN_ID}
        className="mx-auto max-w-6xl px-4 pt-6 pb-[calc(5.5rem_+_env(safe-area-inset-bottom))] md:pb-6"
      >
        <Outlet />
      </main>

      <BottomNav reviewCount={openCount} />
    </div>
  );
}
