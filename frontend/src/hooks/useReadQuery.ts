import { useQuery, type UseQueryOptions, type UseQueryResult } from '@tanstack/react-query';

/**
 * A read as a screen needs to see it: loading, failed with nothing to show, or
 * ready. `refreshFailed` is true when the data is ready but the latest attempt
 * to update it did not work.
 */
export type KeptQuery<TData> = {
  refetch: () => Promise<unknown>;
  refreshFailed: boolean;
} & (
  | { isPending: true; isError: false; isSuccess: false; data: undefined; error: null }
  | { isPending: false; isError: true; isSuccess: false; data: undefined; error: Error }
  | { isPending: false; isError: false; isSuccess: true; data: TData; error: null }
);

/**
 * Applies the rule that a screen is replaced by an error only when there is
 * nothing to show.
 *
 * TanStack Query marks a query as failed even when a background refresh fails
 * while the earlier answer is still held. A phone waking on a poor connection
 * would then lose a good page to a full-screen error. Here the held answer
 * stays "ready" and the failure is reported as `refreshFailed` instead.
 */
export function keepDataOnFailedRefresh<TData>(
  query: UseQueryResult<TData, Error>,
): KeptQuery<TData> {
  const { refetch } = query;
  if (query.data !== undefined) {
    return {
      refetch,
      refreshFailed: query.isError,
      isPending: false,
      isError: false,
      isSuccess: true,
      data: query.data,
      error: null,
    };
  }
  if (query.isError) {
    return {
      refetch,
      refreshFailed: false,
      isPending: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      error: query.error,
    };
  }
  return {
    refetch,
    refreshFailed: false,
    isPending: true,
    isError: false,
    isSuccess: false,
    data: undefined,
    error: null,
  };
}

/** `useQuery` with `keepDataOnFailedRefresh` applied; use it for every read a screen shows. */
export function useReadQuery<TQueryFnData, TData = TQueryFnData>(
  options: UseQueryOptions<TQueryFnData, Error, TData>,
): KeptQuery<TData> {
  return keepDataOnFailedRefresh(useQuery(options));
}
