import { useQuery } from '@tanstack/react-query';
import { categoriesQueryKey, fetchCategories } from '../api/categories';
import { VOCABULARY_STALE_TIME_MS } from '../constants/dashboard';

/** The owner's categories, archived ones included, cached for an hour. */
export function useCategories() {
  return useQuery({
    queryKey: categoriesQueryKey,
    queryFn: fetchCategories,
    staleTime: VOCABULARY_STALE_TIME_MS,
  });
}
