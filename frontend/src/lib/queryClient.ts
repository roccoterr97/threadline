import { QueryClient } from '@tanstack/react-query';
import { QUERY_RETRY_ATTEMPTS, QUERY_STALE_TIME_MS } from '../constants/dashboard';
import { NotConfiguredError, NotSignedInError } from './errors';

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
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying will not fix a missing session or a missing setting.
          if (error instanceof NotSignedInError || error instanceof NotConfiguredError) return false;
          return failureCount < QUERY_RETRY_ATTEMPTS;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}
