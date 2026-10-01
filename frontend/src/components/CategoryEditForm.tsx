import { useState } from 'react';
import * as copy from '../copy/en';
import type { CategoryDraft } from '../domain/categorySettings';
import { useDraftCheck } from '../hooks/useDraftCheck';
import type { Category } from '../types/database';
import { Button } from './Button';
import { CategoryFields } from './CategoryFields';
import { DraftProblemText } from './DraftProblemText';

interface CategoryEditFormProps {
  category: Category;
  /** Every other category, so a name already taken can be turned down. */
  others: readonly Category[];
  /** Called with the trimmed values once they pass every check. */
  onSave: (draft: CategoryDraft) => void;
  onCancel: () => void;
  isBusy: boolean;
}

function draftOf(category: Category): CategoryDraft {
  return {
    label: category.label,
    group_label: category.group_label,
    description: category.description,
    colour: category.colour,
  };
}

/** Changing one category's names, description or colour. Its key stays the same. */
export function CategoryEditForm({
  category,
  others,
  onSave,
  onCancel,
  isBusy,
}: CategoryEditFormProps) {
  const [draft, setDraft] = useState(() => draftOf(category));
  const { formRef, problem, problemId, check } = useDraftCheck(others);
  const actions = copy.categorySettings.actions;

  return (
    <form
      ref={formRef}
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const values = check(draft);
        if (values !== null) onSave(values);
      }}
    >
      <CategoryFields
        draft={draft}
        onChange={setDraft}
        disabled={isBusy}
        problem={problem}
        problemId={problemId}
      />
      <DraftProblemText id={problemId} problem={problem} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" disabled={isBusy}>
          {isBusy ? actions.working : actions.save}
        </Button>
        <Button type="button" onClick={onCancel} disabled={isBusy}>
          {actions.cancel}
        </Button>
      </div>
    </form>
  );
}
