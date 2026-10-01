import type { Vocabulary } from '../domain/vocabulary';
import { useCategories } from './useCategories';
import { useStatusLabels } from './useStatusLabels';

/** Where the owner's vocabulary stands for a screen that needs it. */
export type VocabularyState =
  | { status: 'pending' }
  | { status: 'error'; error: Error; retry: () => void }
  | { status: 'ready'; vocabulary: Vocabulary };

/**
 * The categories and status names together, as one state.
 *
 * Ready only once both have settled, so nothing is drawn with a stand-in name
 * that changes a moment later. The categories are required (without them no
 * person can be placed); the status names never fail, see `useStatusLabels`.
 */
export function useVocabulary(): VocabularyState {
  const categories = useCategories();
  const statusLabels = useStatusLabels();

  if (categories.isError) {
    return {
      status: 'error',
      error: categories.error,
      retry: () => {
        void categories.refetch();
      },
    };
  }
  if (categories.isPending || statusLabels.isPending) return { status: 'pending' };
  return {
    status: 'ready',
    vocabulary: { categories: categories.data, statusLabels: statusLabels.labels },
  };
}
