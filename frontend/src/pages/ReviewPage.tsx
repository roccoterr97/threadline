import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { answerReviewItem, fetchOpenReviewItems, reviewQueryKey } from '../api/review';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { ReviewCard, type ReviewPerson } from '../components/ReviewCard';
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

/**
 * The question that takes the keyboard once `answeredId` leaves the list:
 * the one after it, or the one before when it was the last, or null when
 * none is left.
 */
function questionAfter(items: readonly ReviewItemRow[], answeredId: string): string | null {
  const index = items.findIndex((item) => item.id === answeredId);
  const rest = items.filter((item) => item.id !== answeredId);
  return rest[Math.min(Math.max(index, 0), rest.length - 1)]?.id ?? null;
}

/** Where the keyboard goes next; `itemId` null means the list is now empty. */
interface FocusAfterAnswer {
  itemId: string | null;
}

/**
 * The open questions, answered one card at a time.
 *
 * Answering keeps the owner in the list: the next question takes the
 * keyboard and the saved answer is read out politely, so several questions
 * can be answered in a row without being thrown back to the top.
 */
export function ReviewPage() {
  usePageTitle(copy.review.title);
  const clock = useClock();
  const queryClient = useQueryClient();
  const [failedItemId, setFailedItemId] = useState<string | null>(null);
  const [answered, setAnswered] = useState<string | null>(null);
  const [focusAfterAnswer, setFocusAfterAnswer] = useState<FocusAfterAnswer | null>(null);
  const listDone = useRef<HTMLDivElement>(null);

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
      setAnswered(copy.review.answered[kind][value]);
      // An answer can change who counts as relevant, so both lists are refreshed.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewQueryKey }),
        queryClient.invalidateQueries({ queryKey: peopleQueryKey }),
      ]);
    },
  });

  const isEmpty = items.isSuccess && items.data.length === 0;
  // The last question answered: the keyboard goes to the note that none are left.
  useEffect(() => {
    if (focusAfterAnswer?.itemId !== null || !isEmpty) return;
    listDone.current?.focus();
    setFocusAfterAnswer(null);
  }, [focusAfterAnswer, isEmpty]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.review.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.review.subtitle}</p>
        {/* Always in the page, so each saved answer is read out without moving the keyboard. */}
        <div role="status">
          {answered !== null && (
            <p className="mt-4 rounded-token-lg border border-positive bg-positive-soft p-4 font-medium text-positive">
              {answered}
            </p>
          )}
        </div>
      </div>

      {items.isPending && <LoadingState label={copy.states.loadingReview} />}

      {items.isError && (
        <ErrorState
          error={items.error}
          onRetry={() => {
            void items.refetch();
          }}
        />
      )}

      {isEmpty && (
        <div ref={listDone} tabIndex={-1}>
          <EmptyState title={copy.review.empty.title} body={copy.review.empty.body} />
        </div>
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
              takesFocus={focusAfterAnswer?.itemId === item.id}
              onFocused={() => {
                setFocusAfterAnswer(null);
              }}
              onAnswer={(value) => {
                setFocusAfterAnswer({ itemId: questionAfter(items.data, item.id) });
                answer.mutate({ itemId: item.id, kind: item.kind, answer: value });
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
