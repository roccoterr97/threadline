import { Link, useLocation, useParams } from 'react-router-dom';
import {
  fetchPerson,
  fetchPersonConversations,
  personQueryKey,
  timelineQueryKey,
} from '../api/person';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { InfoNote } from '../components/InfoNote';
import { LoadingState } from '../components/LoadingState';
import { TAP_LINK } from '../components/linkStyles';
import { MarkNoiseAction } from '../components/MarkNoiseAction';
import { PersonCorrection } from '../components/PersonCorrection';
import { PersonHeader } from '../components/PersonHeader';
import { PersonNotes } from '../components/PersonNotes';
import { PersonSummary } from '../components/PersonSummary';
import { RefreshFailedNote } from '../components/RefreshFailedNote';
import { Timeline } from '../components/Timeline';
import { TIMELINE_MESSAGE_LIMIT } from '../constants/dashboard';
import * as copy from '../copy/en';
import { buildTimeline, timelineIsCut } from '../domain/timeline';
import { usePageTitle } from '../hooks/usePageTitle';
import { useReadQuery } from '../hooks/useReadQuery';
import { useVocabulary } from '../hooks/useVocabulary';
import { useClock } from '../lib/ClockContext';
import { personOrigin } from '../lib/personOrigin';

/**
 * One person: who they are, the owner's own notes on them, every message,
 * and — folded away — how to correct the assistant.
 *
 * On a phone everything is one column: summary, notes, then the history, then
 * the correction. On a laptop the history takes the wide left column and the
 * summary, notes and correction sit beside it, so the messages start at the top.
 * Every way back goes to the list the person was opened from (People, or an
 * organisation's page) with the filters and order it had.
 */
export function PersonPage() {
  const clock = useClock();
  const { personId = '' } = useParams<{ personId: string }>();
  const origin = personOrigin(useLocation().state);

  const person = useReadQuery({
    queryKey: personQueryKey(personId),
    queryFn: () => fetchPerson(personId),
  });
  const conversations = useReadQuery({
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
          <Link to={origin.address} state={origin.state} className={`font-medium ${TAP_LINK}`}>
            {origin.label}
          </Link>
        }
      />
    );
  }

  const timeline = buildTimeline(conversations.data ?? []);

  return (
    <div className="flex flex-col gap-6">
      <Link to={origin.address} state={origin.state} className={`self-start ${TAP_LINK}`}>
        {origin.label}
      </Link>

      <RefreshFailedNote
        show={person.refreshFailed || conversations.refreshFailed || vocabulary.refreshFailed}
      />

      <PersonHeader person={person.data} vocabulary={vocabulary.vocabulary} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-[auto_1fr] lg:items-start">
        <div className="flex flex-col gap-4 lg:col-start-2 lg:row-start-1">
          <PersonSummary person={person.data} clock={clock} />
          <PersonNotes personId={personId} />
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
          {conversations.isSuccess && timelineIsCut(conversations.data) && (
            <InfoNote>{copy.person.timelineCut(TIMELINE_MESSAGE_LIMIT)}</InfoNote>
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
