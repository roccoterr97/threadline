import { useState } from 'react';
import * as copy from '../copy/en';
import {
  canAddCategory,
  categoryKeyFromName,
  findDraftProblem,
  firstFreeColour,
  nextSortOrder,
  suggestedGroupLabel,
  trimDraft,
  type CategoryDraft,
  type DraftProblem,
} from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category } from '../types/database';
import { Button } from './Button';
import { CategoryFields } from './CategoryFields';
import { DraftProblemText } from './DraftProblemText';
import { LimitNote } from './LimitNote';
import { SettingsSection } from './SettingsSection';

const actions = copy.categorySettings.actions;

interface AddCategoryFormProps {
  categories: readonly Category[];
  editor: CategoryEditor;
}

function emptyDraft(categories: readonly Category[]): CategoryDraft {
  return { label: '', group_label: '', description: '', colour: firstFreeColour(categories) };
}

/**
 * The group name follows the name ("Customer" → "Customers") until the owner
 * types a group name of their own.
 */
function followName(previous: CategoryDraft, next: CategoryDraft): CategoryDraft {
  const groupWasSuggested = previous.group_label === suggestedGroupLabel(previous.label);
  if (!groupWasSuggested || previous.label === next.label) return next;
  return { ...next, group_label: suggestedGroupLabel(next.label) };
}

/** "Add your own": a new category from a name, a group name, who belongs and a colour. */
export function AddCategoryForm({ categories, editor }: AddCategoryFormProps) {
  const [draft, setDraft] = useState(() => emptyDraft(categories));
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  const canAdd = canAddCategory(categories);

  const submit = () => {
    const found = findDraftProblem(draft);
    setProblem(found);
    if (found !== null) return;
    const values = trimDraft(draft);
    const keys = categories.map((category) => category.key);
    const category = {
      ...values,
      key: categoryKeyFromName(values.label, keys),
      sort_order: nextSortOrder(categories),
    };
    editor.run({ kind: 'add', category }, () => {
      setDraft(emptyDraft([...categories, { ...category, archived_at: null }]));
    });
  };

  return (
    <SettingsSection title={copy.categorySettings.addOwn}>
      {!canAdd && <LimitNote />}
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <CategoryFields
          draft={draft}
          disabled={editor.isBusy || !canAdd}
          onChange={(next) => {
            setDraft((previous) => followName(previous, next));
          }}
        />
        <DraftProblemText problem={problem} />
        <div>
          <Button type="submit" variant="primary" disabled={editor.isBusy || !canAdd}>
            {editor.isBusy ? actions.working : actions.add}
          </Button>
        </div>
      </form>
    </SettingsSection>
  );
}
