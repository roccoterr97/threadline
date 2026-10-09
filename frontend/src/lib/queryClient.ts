import { QueryClient } from '@tanstack/react-query';
import { QUERY_RETRY_ATTEMPTS, QUERY_STALE_TIME_MS } from '../constants/dashboard';
import { NotAllowedError, NotConfiguredError, NotSignedInError } from './errors';

/**
 * Creates the query cache.
 *
 * Everything lives in memory only: message text is never written to disk, so
 * closing the tab leaves nothing behind.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: QUERY_STALE_TIME_MS,
        // A tab or home-screen app can stay open for days. Coming back to it
        // reloads whatever has gone stale, so Monday's overdue badges are not
        // shown on Tuesday. Fresh data (see staleTime) is left alone, and a
        // reload only swaps the data: text typed into a form lives in the
        // form, not in the query cache, so nothing being edited is reset.
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          // Retrying will not fix a missing session, a refused account or a missing setting.
          if (
            error instanceof NotSignedInError ||
            error instanceof NotAllowedError ||
            error instanceof NotConfiguredError
          ) {
            return false;
          }
          return failureCount < QUERY_RETRY_ATTEMPTS;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}
