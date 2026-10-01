import { useQuery } from '@tanstack/react-query';
import { fetchStatusLabels, statusLabelsQueryKey } from '../api/statusLabels';
import { VOCABULARY_STALE_TIME_MS } from '../constants/dashboard';
import * as copy from '../copy/en';
import { resolveStatusLabels, type StatusLabels } from '../domain/vocabulary';

interface StatusLabelsState {
  /** Always complete: the owner's names, or the neutral defaults where missing. */
  labels: StatusLabels;
  /** True until the first answer (or final failure) — wait on it to avoid a flicker. */
  isPending: boolean;
}

/**
 * The owner's names for the six statuses.
 *
 * The labels are never missing: a status with no row, or every status when the
 * table cannot be read, falls back to the neutral names in `copy`. A failure
 * is therefore not an error state — the screen still says something true.
 */
export function useStatusLabels(): StatusLabelsState {
  const query = useQuery({
    queryKey: statusLabelsQueryKey,
    queryFn: fetchStatusLabels,
    staleTime: VOCABULARY_STALE_TIME_MS,
  });
  return {
    labels: resolveStatusLabels(query.data, copy.defaultStatusLabels),
    isPending: query.isPending,
  };
}
