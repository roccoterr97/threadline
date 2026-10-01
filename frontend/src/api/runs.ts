import { z } from 'zod';
import { RUN_HISTORY_LIMIT } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import { runQuery } from './client';
import { runWithStepsSchema, type RunWithSteps } from './schemas';

const runsSchema = z.array(runWithStepsSchema);

export const runsQueryKey = ['runs'] as const;

/** The most recent automatic updates, newest first, each with its steps. */
export async function fetchRecentRuns(): Promise<RunWithSteps[]> {
  const supabase = getSupabaseClient();
  return runQuery('runs.list', runsSchema, () =>
    supabase
      .from('run_logs')
      .select('*, run_step_logs(*)')
      .order('started_at', { ascending: false })
      .limit(RUN_HISTORY_LIMIT),
  );
}
