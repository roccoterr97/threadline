import { useState } from 'react';
import * as copy from '../copy/en';
import {
  canAddCategory,
  categoryKeyFromName,
  firstFreeColour,
  nextSortOrder,
  suggestedGroupLabel,
  type CategoryDraft,
} from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import { useDraftCheck } from '../hooks/useDraftCheck';
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

/**
 * "Add your own": a new category from a name, a group name, who belongs and a
 * colour. The colour starts on the first one no category uses, and keeps
 * following it (as categories are added elsewhere on the page) until the owner
 * picks one.
 */
export function AddCategoryForm({ categories, editor }: AddCategoryFormProps) {
  const [typed, setDraft] = useState(() => emptyDraft(categories));
  const [colourPicked, setColourPicked] = useState(false);
  const draft = colourPicked ? typed : { ...typed, colour: firstFreeColour(categories) };
  const { formRef, problem, problemId, check } = useDraftCheck(categories);
  const canAdd = canAddCategory(categories);

  const submit = () => {
    const values = check(draft);
    if (values === null) return;
    const keys = categories.map((category) => category.key);
    const category = {
      ...values,
      key: categoryKeyFromName(values.label, keys),
      sort_order: nextSortOrder(categories),
    };
    editor.run(
      { kind: 'add', category },
      {
        onSaved: () => {
          setDraft(emptyDraft([...categories, { ...category, archived_at: null }]));
          setColourPicked(false);
        },
      },
    );
  };

  return (
    <SettingsSection title={copy.categorySettings.addOwn}>
      {!canAdd && <LimitNote />}
      <form
        ref={formRef}
        noValidate
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
            if (next.colour !== draft.colour) setColourPicked(true);
            setDraft((previous) => followName(previous, next));
          }}
          problem={problem}
          problemId={problemId}
        />
        <DraftProblemText id={problemId} problem={problem} />
        <div>
          <Button type="submit" variant="primary" disabled={editor.isBusy || !canAdd}>
            {editor.isBusy ? actions.working : actions.add}
          </Button>
        </div>
      </form>
    </SettingsSection>
  );
}
