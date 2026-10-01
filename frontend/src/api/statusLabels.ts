import { z } from 'zod';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { StatusLabel } from '../types/database';
import { runQuery } from './client';
import { statusLabelSchema } from './schemas';

/** A list of status labels, as the status-labels query returns it. */
export const statusLabelListSchema = z.array(statusLabelSchema);

export const statusLabelsQueryKey = ['status-labels'] as const;

/** The owner's name for each status. At most one row per status, so six at most. */
export async function fetchStatusLabels(): Promise<StatusLabel[]> {
  const supabase = getSupabaseClient();
  return runQuery('status_labels.list', statusLabelListSchema, () =>
    supabase.from('status_labels').select('status,label'),
  );
}
