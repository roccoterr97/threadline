import { z } from 'zod';
import { CATEGORIES_LIMIT } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { Category } from '../types/database';
import { runQuery } from './client';
import { categorySchema } from './schemas';

/** A list of categories, as the categories query returns it. */
export const categoryListSchema = z.array(categorySchema);

export const categoriesQueryKey = ['categories'] as const;

/** The columns the dashboard reads; `description` is shown on the settings page. */
const CATEGORY_COLUMNS = 'key,label,group_label,description,colour,sort_order,archived_at';

/**
 * Every category, archived ones included, in the order the dashboard shows
 * them. Archived ones are kept because some people may still carry one.
 */
export async function fetchCategories(): Promise<Category[]> {
  const supabase = getSupabaseClient();
  return runQuery('categories.list', categoryListSchema, () =>
    supabase
      .from('categories')
      .select(CATEGORY_COLUMNS)
      .order('sort_order', { ascending: true })
      .order('key', { ascending: true })
      .limit(CATEGORIES_LIMIT),
  );
}
