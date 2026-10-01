import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { categoriesQueryKey } from '../api/categories';
import {
  addCategory,
  removeCategory,
  RemovalOutcome,
  saveCategoryOrder,
  showCategoryAgain,
  updateCategory,
} from '../api/categoryEdits';
import { categorySuggestionsQueryKey } from '../api/categorySuggestions';
import type { SaveOutcome } from '../components/SaveFeedback';
import * as copy from '../copy/en';
import { problemForIndex, type SortChange } from '../domain/categorySettings';
import { useClock } from '../lib/ClockContext';
import { NotSignedInError, RefusalReason, RefusedError } from '../lib/errors';
import type { CategoryChanges, CategoryInsert, CategoryKey } from '../types/database';

/** One change the settings page can make. `label` names it in the feedback. */
export type CategoryAction =
  | { kind: 'add'; category: CategoryInsert }
  | { kind: 'update'; key: CategoryKey; label: string; changes: CategoryChanges }
  | { kind: 'move'; label: string; changes: readonly SortChange[] }
  | { kind: 'remove'; key: CategoryKey; label: string }
  | { kind: 'show-again'; key: CategoryKey; label: string };

/** What a caller wants to hear back about one change. */
export interface RunCallbacks {
  /** Runs only if the change was saved. */
  onSaved?: () => void;
  /** Runs once the change has ended either way and the list has been fetched again. */
  onSettled?: () => void;
}

/** What the settings page's parts need to change categories. */
export interface CategoryEditor {
  /** Starts a change. */
  run: (action: CategoryAction, callbacks?: RunCallbacks) => void;
  /** True while a change is on its way; every control waits for it. */
  isBusy: boolean;
  /** How the most recent change ended, or null while none has or one is waiting. */
  feedback: SaveOutcome | null;
}

const done = copy.categorySettings.done;
const failed = copy.categorySettings.failed;

/** Carries out one action and returns the sentence that says it worked. */
async function perform(action: CategoryAction, now: Date): Promise<string> {
  switch (action.kind) {
    case 'add':
      await addCategory(action.category);
      return done.added(action.category.label);
    case 'update':
      await updateCategory(action.key, action.changes);
      return done.saved(action.label);
    case 'move':
      await saveCategoryOrder(action.changes);
      return done.moved(action.label);
    case 'remove': {
      const outcome = await removeCategory(action.key, now);
      return outcome === RemovalOutcome.Deleted
        ? done.removed(action.label)
        : done.hiddenInstead(action.label);
    }
    case 'show-again':
      await showCategoryAgain(action.key);
      return done.shownAgain(action.label);
  }
}

/** Turns a failure into one sentence the owner can act on; never the database's words. */
export function categoryEditFailureText(error: Error): string {
  if (error instanceof NotSignedInError) return failed.signedOut;
  if (!(error instanceof RefusedError)) return failed.generic;
  if (error.reason === RefusalReason.BreaksRule) return failed.breaksRule;
  if (error.reason !== RefusalReason.Duplicate) return failed.generic;
  const problem = problemForIndex(error.constraint);
  return problem === null ? failed.duplicate : copy.categoryDraftProblems[problem];
}

/**
 * Changing the owner's categories from the settings page.
 *
 * One change runs at a time, so two quick taps can never race each other.
 * After each change the categories and the suggestions are fetched again, so
 * the page always shows what the database now holds.
 */
export function useCategoryEditor(): CategoryEditor {
  const queryClient = useQueryClient();
  const clock = useClock();
  const [feedback, setFeedback] = useState<SaveOutcome | null>(null);

  const mutation = useMutation<string, Error, CategoryAction>({
    mutationFn: (action) => perform(action, clock.now()),
    onMutate: () => {
      setFeedback(null);
    },
    // A move keeps the keyboard on the moved row, so its sentence must not take focus.
    onSuccess: (text, action) => {
      setFeedback({ tone: 'success', text, keepFocus: action.kind === 'move' });
    },
    onError: (error, action) => {
      const text = categoryEditFailureText(error);
      setFeedback({ tone: 'error', text, keepFocus: action.kind === 'move' });
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: categoriesQueryKey }),
        queryClient.invalidateQueries({ queryKey: categorySuggestionsQueryKey }),
      ]);
    },
  });

  return {
    run: (action, callbacks = {}) => {
      mutation.mutate(action, { onSuccess: callbacks.onSaved, onSettled: callbacks.onSettled });
    },
    isBusy: mutation.isPending,
    feedback,
  };
}
