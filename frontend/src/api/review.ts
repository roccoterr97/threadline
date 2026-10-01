import { z } from 'zod';
import { REVIEW_PAGE_SIZE } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import type { ReviewAnswer, ReviewItemRow } from '../types/database';
import { runMutation, runQuery } from './client';
import { reviewItemRowSchema } from './schemas';

const reviewListSchema = z.array(reviewItemRowSchema);

export const reviewQueryKey = ['review', 'open'] as const;

/** Every question the assistant is still waiting on, oldest first. */
export async function fetchOpenReviewItems(): Promise<ReviewItemRow[]> {
  const supabase = getSupabaseClient();
  return runQuery('review.list', reviewListSchema, () =>
    supabase
      .from('review_items')
      .select('*')
      .is('answer', null)
      .order('created_at', { ascending: true })
      .limit(REVIEW_PAGE_SIZE),
  );
}

/**
 * Stores a Yes/No answer and the moment it was given.
 *
 * @param answeredAt Passed in rather than read from the clock here, so the
 *   caller — and the tests — decide what "now" means.
 */
export async function answerReviewItem(
  itemId: string,
  answer: ReviewAnswer,
  answeredAt: Date,
): Promise<void> {
  const supabase = getSupabaseClient();
  await runMutation('review.answer', () =>
    supabase
      .from('review_items')
      .update({ answer, answered_at: answeredAt.toISOString() })
      .eq('id', itemId),
  );
}
