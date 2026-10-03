import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  fetchPerson,
  fetchPersonConversations,
  personQueryKey,
  timelineQueryKey,
} from '../api/person';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { MarkNoiseAction } from '../components/MarkNoiseAction';
import { PersonCorrection } from '../components/PersonCorrection';
import { PersonHeader } from '../components/PersonHeader';
import { PersonSummary } from '../components/PersonSummary';
import { Timeline } from '../components/Timeline';
import * as copy from '../copy/en';
import { buildTimeline } from '../domain/timeline';
import { usePageTitle } from '../hooks/usePageTitle';
import { useVocabulary } from '../hooks/useVocabulary';
import { useClock } from '../lib/ClockContext';
import { peopleListAddress } from '../lib/peopleListAddress';

/**
 * One person: who they are, every message, and — folded away — how to correct
 * the assistant.
 *
 * On a phone everything is one column: summary, then the history, then the
 * correction. On a laptop the history takes the wide left column and the
 * summary and correction sit beside it, so the messages start at the top.
 * Every way back to People keeps the filters and order it was opened with.
 */
export function PersonPage() {
  const clock = useClock();
  const { personId = '' } = useParams<{ personId: string }>();
  const peopleAddress = peopleListAddress(useLocation().state);

  const person = useQuery({
    queryKey: personQueryKey(personId),
    queryFn: () => fetchPerson(personId),
  });
  const conversations = useQuery({
    queryKey: timelineQueryKey(personId),
    queryFn: () => fetchPersonConversations(personId),
  });
  const vocabulary = useVocabulary();
  usePageTitle(person.data === null ? copy.person.notFound.title : (person.data?.full_name ?? null));

  if (person.isError) {
    return (
      <ErrorState
        error={person.error}
        onRetry={() => {
          void person.refetch();
        }}
      />
    );
  }

  if (vocabulary.status === 'error') {
    return <ErrorState error={vocabulary.error} onRetry={vocabulary.retry} />;
  }

  if (person.isPending || vocabulary.status === 'pending') {
    return <LoadingState label={copy.states.loadingPerson} />;
  }

  if (person.data === null) {
    return (
      <EmptyState
        title={copy.person.notFound.title}
        body={copy.person.notFound.body}
        action={
          <Link to={peopleAddress} className="font-medium text-accent underline underline-offset-2">
            {copy.person.backToPeople}
          </Link>
        }
      />
    );
  }

  const timeline = buildTimeline(conversations.data ?? []);

  return (
    <div className="flex flex-col gap-6">
      <Link to={peopleAddress} className="self-start text-accent underline underline-offset-2">
        {copy.person.backToPeople}
      </Link>

      <PersonHeader person={person.data} vocabulary={vocabulary.vocabulary} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-[auto_1fr] lg:items-start">
        <div className="lg:col-start-2 lg:row-start-1">
          <PersonSummary person={person.data} clock={clock} />
        </div>

        <section className="flex min-w-0 flex-col gap-3 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <h2 className="text-lg font-semibold text-ink">{copy.person.timelineTitle}</h2>
          {conversations.isPending && <LoadingState label={copy.states.loading} />}
          {conversations.isError && (
            <ErrorState
              error={conversations.error}
              onRetry={() => {
                void conversations.refetch();
              }}
            />
          )}
          {conversations.isSuccess && timeline.length === 0 && (
            <EmptyState title={copy.person.timelineTitle} body={copy.person.timelineEmpty} />
          )}
          {timeline.length > 0 && <Timeline entries={timeline} />}
        </section>

        <div className="flex flex-col gap-4 lg:col-start-2 lg:row-start-2">
          <PersonCorrection personId={personId} vocabulary={vocabulary.vocabulary} />
          <MarkNoiseAction personId={personId} personName={person.data.full_name} />
        </div>
      </div>
    </div>
  );
}
