import { useQuery } from '@tanstack/react-query';
import { useId } from 'react';
import {
  categorySuggestionsQueryKey,
  fetchCategorySuggestions,
} from '../api/categorySuggestions';
import { AddCategoryForm } from '../components/AddCategoryForm';
import { CategoryList } from '../components/CategoryList';
import { ErrorState } from '../components/ErrorState';
import { HiddenCategories } from '../components/HiddenCategories';
import { LoadingState } from '../components/LoadingState';
import { SaveFeedback } from '../components/SaveFeedback';
import { SuggestionChips } from '../components/SuggestionChips';
import { VOCABULARY_STALE_TIME_MS } from '../constants/dashboard';
import * as copy from '../copy/en';
import { useCategories } from '../hooks/useCategories';
import { useCategoryEditor } from '../hooks/useCategoryEditor';

/**
 * The settings page. Today it holds one thing: the owner's categories, which
 * are the source of truth for how people are sorted — the preset's
 * categories are only offered as suggestions.
 */
export function SettingsPage() {
  const headingId = useId();
  const categories = useCategories();
  const suggestions = useQuery({
    queryKey: categorySuggestionsQueryKey,
    queryFn: fetchCategorySuggestions,
    staleTime: VOCABULARY_STALE_TIME_MS,
  });
  const editor = useCategoryEditor();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.settings.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.settings.subtitle}</p>
      </div>

      <section aria-labelledby={headingId} className="flex flex-col gap-6">
        <div>
          <h2 id={headingId} className="text-xl font-semibold text-ink">
            {copy.categorySettings.title}
          </h2>
          <p className="mt-1 max-w-prose text-ink-muted">{copy.categorySettings.intro}</p>
        </div>

        {editor.feedback !== null && <SaveFeedback outcome={editor.feedback} />}

        {categories.isPending && <LoadingState label={copy.settings.loading} />}

        {categories.isError && (
          <ErrorState
            error={categories.error}
            onRetry={() => {
              void categories.refetch();
            }}
          />
        )}

        {categories.isSuccess && (
          <>
            <CategoryList categories={categories.data} editor={editor} />
            <HiddenCategories categories={categories.data} editor={editor} />
            {suggestions.isError && (
              <p className="text-sm text-ink-muted">{copy.categorySettings.suggestionsFailed}</p>
            )}
            {suggestions.isSuccess && (
              <SuggestionChips
                categories={categories.data}
                suggestions={suggestions.data}
                editor={editor}
              />
            )}
            <AddCategoryForm categories={categories.data} editor={editor} />
          </>
        )}
      </section>
    </div>
  );
}
