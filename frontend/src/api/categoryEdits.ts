import { RefusalReason, RefusedError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { CategoryChanges, CategoryInsert, CategoryKey } from '../types/database';
import type { SortChange } from '../domain/categorySettings';
import { runMutation } from './client';

/**
 * Every change the settings page makes to the `categories` table. The key of
 * a category never changes; renaming one only changes its label.
 */

/** How a removal ended: gone for good, or hidden because people still have it. */
export enum RemovalOutcome {
  Deleted = 'deleted',
  Archived = 'archived',
}

/** Adds one of the owner's categories. */
export async function addCategory(category: CategoryInsert): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('categories.add', () => supabase.from('categories').insert(category));
}

/** Changes the name, group name, description, colour, position or hidden state. */
export async function updateCategory(key: CategoryKey, changes: CategoryChanges): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('categories.update', () =>
    supabase.from('categories').update(changes).eq('key', key),
  );
}

/** Saves new positions. Each row is one update; the list is at most eight long. */
export async function saveCategoryOrder(changes: readonly SortChange[]): Promise<void> {
  await Promise.all(
    changes.map((change) => updateCategory(change.key, { sort_order: change.sort_order })),
  );
}

/** Puts a hidden category back among the choices. */
export async function showCategoryAgain(key: CategoryKey): Promise<void> {
  await updateCategory(key, { archived_at: null });
}

/**
 * Removes a category. The database refuses to delete one that a person or a
 * correction still has; that category is hidden instead, so those people keep
 * it while it is no longer offered as a choice.
 *
 * @param now When the category counts as hidden from, if it has to be.
 */
export async function removeCategory(key: CategoryKey, now: Date): Promise<RemovalOutcome> {
  const supabase = getSupabaseClient();
  try {
    await runMutation('categories.delete', () =>
      supabase.from('categories').delete().eq('key', key),
    );
    return RemovalOutcome.Deleted;
  } catch (error) {
    if (!(error instanceof RefusedError) || error.reason !== RefusalReason.InUse) throw error;
  }
  await updateCategory(key, { archived_at: now.toISOString() });
  return RemovalOutcome.Archived;
}
