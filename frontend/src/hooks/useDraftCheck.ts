import { useId, useState } from 'react';
import {
  findDraftProblem,
  trimDraft,
  type CategoryDraft,
  type DraftProblem,
} from '../domain/categorySettings';
import type { Category } from '../types/database';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

/**
 * Checking a category form before it is saved: what is wrong (if anything),
 * the id of the sentence that says so, and focus moved to the field at fault.
 *
 * @param others Every other category, so a name already taken is turned down.
 */
export function useDraftCheck(others: readonly Category[]) {
  const problemId = useId();
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  const { container: formRef, afterCheck } = useFocusFirstInvalid<HTMLFormElement>();

  /** The trimmed draft when it can be saved, or null after marking what is wrong. */
  const check = (draft: CategoryDraft): CategoryDraft | null => {
    const found = findDraftProblem(draft, others);
    setProblem(found);
    afterCheck();
    return found === null ? trimDraft(draft) : null;
  };

  return { formRef, problem, problemId, check };
}
