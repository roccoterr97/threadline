import { useQuery } from '@tanstack/react-query';
import { categoriesQueryKey, fetchCategories } from '../api/categories';
import { VOCABULARY_STALE_TIME_MS } from '../constants/dashboard';
import * as copy from '../copy/en';
import { nameReservedCategory } from '../domain/categories';
import type { Category } from '../types/database';

function withReservedName(categories: Category[]): Category[] {
  return nameReservedCategory(categories, copy.values.unknown);
}

/**
 * The owner's categories, archived ones included, cached for an hour. The
 * reserved one is shown under the dashboard's own word for "not known".
 */
export function useCategories() {
  return useQuery({
    queryKey: categoriesQueryKey,
    queryFn: fetchCategories,
    staleTime: VOCABULARY_STALE_TIME_MS,
    select: withReservedName,
  });
}
