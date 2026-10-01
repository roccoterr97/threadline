import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { answerReviewItem, fetchOpenReviewItems, reviewQueryKey } from '../api/review';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { ReviewCard, type ReviewPerson } from '../components/ReviewCard';
import { SaveFeedback, type SaveOutcome } from '../components/SaveFeedback';
import * as copy from '../copy/en';
import { usePageTitle } from '../hooks/usePageTitle';
import { useClock } from '../lib/ClockContext';
import type { PeopleOverviewRow, ReviewAnswer, ReviewItemRow } from '../types/database';

interface AnswerInput {
  itemId: string;
  kind: ReviewItemRow['kind'];
  answer: ReviewAnswer;
}

/**
 * The people a question names who are on the list, so their pages can be
 * opened. Someone the assistant is still unsure about is not on the list yet
 * and has no page, so they get no link.
 */
function listedPeople(item: ReviewItemRow, people: readonly PeopleOverviewRow[]): ReviewPerson[] {
  return [item.person_id, item.other_person_id].flatMap((id) => {
    const person = id === null ? undefined : people.find((row) => row.person_id === id);
    return person === undefined ? [] : [{ id: person.person_id, name: person.full_name }];
  });
}

/** The open questions, answered one card at a time. */
export function ReviewPage() {
  usePageTitle(copy.review.title);
  const clock = useClock();
  const queryClient = useQueryClient();
  const [failedItemId, setFailedItemId] = useState<string | null>(null);
  const [answered, setAnswered] = useState<SaveOutcome | null>(null);

  const items = useQuery({ queryKey: reviewQueryKey, queryFn: fetchOpenReviewItems });
  // Only for the links to each person; the questions show fine without it.
  const people = useQuery({ queryKey: peopleQueryKey, queryFn: fetchPeople });

  const answer = useMutation<void, Error, AnswerInput, ReviewItemRow[] | undefined>({
    mutationFn: ({ itemId, answer: value }) => answerReviewItem(itemId, value, clock.now()),
    onMutate: async ({ itemId }) => {
      setFailedItemId(null);
      setAnswered(null);
      await queryClient.cancelQueries({ queryKey: reviewQueryKey });
      const previous = queryClient.getQueryData<ReviewItemRow[]>(reviewQueryKey);
      // The answered card disappears straight away; the count in the navigation
      // reads the same list, so it drops at the same moment.
      queryClient.setQueryData<ReviewItemRow[]>(
        reviewQueryKey,
        (current) => current?.filter((item) => item.id !== itemId) ?? [],
      );
      return previous;
    },
    onError: (_error, { itemId }, previous) => {
      queryClient.setQueryData(reviewQueryKey, previous);
      setFailedItemId(itemId);
    },
    onSuccess: async (_result, { kind, answer: value }) => {
      setAnswered({ tone: 'success', text: copy.review.answered[kind][value] });
      // An answer can change who counts as relevant, so both lists are refreshed.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewQueryKey }),
        queryClient.invalidateQueries({ queryKey: peopleQueryKey }),
      ]);
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.review.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.review.subtitle}</p>
      </div>

      {answered !== null && <SaveFeedback outcome={answered} />}

      {items.isPending && <LoadingState label={copy.states.loadingReview} />}

      {items.isError && (
        <ErrorState
          error={items.error}
          onRetry={() => {
            void items.refetch();
          }}
        />
      )}

      {items.isSuccess && items.data.length === 0 && (
        <EmptyState title={copy.review.empty.title} body={copy.review.empty.body} />
      )}

      {items.isSuccess && items.data.length > 0 && (
        <ul className="flex list-none flex-col gap-3 p-0">
          {items.data.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              people={listedPeople(item, people.data ?? [])}
              isAnswering={answer.isPending && answer.variables?.itemId === item.id}
              errorText={failedItemId === item.id ? copy.review.failed : null}
              onAnswer={(value) => {
                answer.mutate({ itemId: item.id, kind: item.kind, answer: value });
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
