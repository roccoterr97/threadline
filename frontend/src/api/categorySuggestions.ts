import { z } from 'zod';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { CategorySuggestion } from '../types/database';
import { runQuery } from './client';
import { categorySuggestionSchema } from './schemas';

/** A list of suggestions, as the suggestions query returns it. */
export const categorySuggestionListSchema = z.array(categorySuggestionSchema);

export const categorySuggestionsQueryKey = ['category-suggestions'] as const;

/** The categories the owner's chosen preset suggests, in the preset's order. */
export async function fetchCategorySuggestions(): Promise<CategorySuggestion[]> {
  const supabase = getSupabaseClient();
  return runQuery('category_suggestions.list', categorySuggestionListSchema, () =>
    supabase
      .from('category_suggestions')
      .select('key,label,group_label,description,colour')
      .order('sort_order', { ascending: true })
      .order('key', { ascending: true }),
  );
}
