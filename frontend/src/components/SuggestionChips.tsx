import * as copy from '../copy/en';
import { canAddCategory, nextSortOrder, suggestionsToOffer } from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category, CategorySuggestion } from '../types/database';
import { LimitNote } from './LimitNote';
import { SettingsSection } from './SettingsSection';
import { TypeDot } from './TypeDot';

interface SuggestionChipsProps {
  categories: readonly Category[];
  suggestions: readonly CategorySuggestion[];
  editor: CategoryEditor;
}

const CHIP =
  'inline-flex min-h-11 items-center gap-2 rounded-token-md border border-line-strong bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-neutral-soft disabled:cursor-not-allowed disabled:opacity-60';

/**
 * The preset's categories the owner does not have yet, each added with one
 * tap, description and colour included. Absent when there is nothing to offer.
 */
export function SuggestionChips({ categories, suggestions, editor }: SuggestionChipsProps) {
  const offered = suggestionsToOffer(suggestions, categories);
  if (offered.length === 0) return null;
  const canAdd = canAddCategory(categories);

  const add = (suggestion: CategorySuggestion) => {
    editor.run({
      kind: 'add',
      category: { ...suggestion, sort_order: nextSortOrder(categories) },
    });
  };

  return (
    <SettingsSection
      title={copy.categorySettings.suggestions}
      intro={copy.categorySettings.suggestionsIntro}
    >
      {!canAdd && <LimitNote />}
      <div className="flex flex-wrap gap-2">
        {offered.map((suggestion) => (
          <button
            key={suggestion.key}
            type="button"
            className={CHIP}
            disabled={editor.isBusy || !canAdd}
            onClick={() => {
              add(suggestion);
            }}
          >
            <TypeDot colour={suggestion.colour} />
            {copy.categorySettings.actions.addSuggestion(suggestion.label)}
          </button>
        ))}
      </div>
    </SettingsSection>
  );
}
