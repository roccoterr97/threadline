import { useState } from 'react';
import * as copy from '../copy/en';
import {
  findDraftProblem,
  trimDraft,
  type CategoryDraft,
  type DraftProblem,
} from '../domain/categorySettings';
import type { Category } from '../types/database';
import { Button } from './Button';
import { CategoryFields } from './CategoryFields';
import { DraftProblemText } from './DraftProblemText';

interface CategoryEditFormProps {
  category: Category;
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
export function CategoryEditForm({ category, onSave, onCancel, isBusy }: CategoryEditFormProps) {
  const [draft, setDraft] = useState(() => draftOf(category));
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  const actions = copy.categorySettings.actions;

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const found = findDraftProblem(draft);
        setProblem(found);
        if (found === null) onSave(trimDraft(draft));
      }}
    >
      <CategoryFields draft={draft} onChange={setDraft} disabled={isBusy} />
      <DraftProblemText problem={problem} />
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
