import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { fetchUpcomingMeetings, upcomingMeetingsQueryKey } from '../api/meetings';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { fetchRecentRuns, runsQueryKey } from '../api/runs';
import { Button } from '../components/Button';
import { ComingUp } from '../components/ComingUp';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { HeadlineCounters } from '../components/HeadlineCounters';
import { LoadingState } from '../components/LoadingState';
import { PeopleFilters } from '../components/PeopleFilters';
import { PeopleTable } from '../components/PeopleTable';
import { RunBanner } from '../components/RunBanner';
import { StatusGrid } from '../components/StatusGrid';
import * as copy from '../copy/en';
import { categoriesInUse } from '../domain/categories';
import { countByTypeAndStatus, countPeople } from '../domain/counters';
import {
  applyPeopleView,
  clearFilters,
  DEFAULT_FILTERS,
  readPeopleView,
  writePeopleView,
  type PeopleView,
  type StatusFilter,
  type TypeFilter,
} from '../domain/peopleView';
import { assessRunHealth } from '../domain/runHealth';
import { useVocabulary } from '../hooks/useVocabulary';
import { useClock } from '../lib/ClockContext';

/** The home screen: how things stand, then everyone, filtered and sorted. */
export function HomePage() {
  const clock = useClock();
  const [searchParams, setSearchParams] = useSearchParams();

  const people = useQuery({ queryKey: peopleQueryKey, queryFn: fetchPeople });
  const vocabularyState = useVocabulary();
  const runs = useQuery({ queryKey: runsQueryKey, queryFn: fetchRecentRuns });
  const meetings = useQuery({
    queryKey: upcomingMeetingsQueryKey,
    queryFn: () => fetchUpcomingMeetings(clock.now()),
  });

  const allPeople = people.data ?? [];
  const vocabulary = vocabularyState.status === 'ready' ? vocabularyState.vocabulary : null;
  // Until the categories are known no `type` in the address can be trusted, so it reads as "all".
  const typeOptions = vocabulary === null ? [] : categoriesInUse(vocabulary.categories, allPeople);
  const view = readPeopleView(searchParams, typeOptions.map((category) => category.key));
  const ready = people.isSuccess && vocabulary !== null;
  const failed = people.isError || vocabularyState.status === 'error';
  const counters = countPeople(allPeople);
  const visiblePeople = applyPeopleView(allPeople, view);

  const showView = (next: PeopleView) => {
    setSearchParams(writePeopleView(next));
  };
  const gridLink = (type: TypeFilter, status: StatusFilter) =>
    `?${writePeopleView({ ...DEFAULT_FILTERS, type, status, sort: view.sort }).toString()}`;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.home.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.home.subtitle}</p>
      </div>

      {runs.isSuccess && <RunBanner health={assessRunHealth(runs.data, clock)} clock={clock} />}

      {/* The strip is extra: while it loads, nothing shows rather than a second spinner. */}
      {meetings.isSuccess && <ComingUp meetings={meetings.data} />}
      {meetings.isError && <p className="text-sm text-ink-muted">{copy.home.comingUp.failed}</p>}

      <HeadlineCounters counters={counters} view={view} />

      {ready && allPeople.length > 0 && (
        <StatusGrid
          grid={countByTypeAndStatus(allPeople, vocabulary.categories)}
          statusLabels={vocabulary.statusLabels}
          linkFor={gridLink}
        />
      )}

      {vocabulary !== null && (
        <PeopleFilters
          view={view}
          categories={typeOptions}
          statusLabels={vocabulary.statusLabels}
          onChange={showView}
        />
      )}

      {!ready && !failed && <LoadingState label={copy.states.loadingPeople} />}

      {people.isError && (
        <ErrorState
          error={people.error}
          onRetry={() => {
            void people.refetch();
          }}
        />
      )}

      {vocabularyState.status === 'error' && !people.isError && (
        <ErrorState error={vocabularyState.error} onRetry={vocabularyState.retry} />
      )}

      {ready && allPeople.length === 0 && (
        <EmptyState title={copy.home.empty.title} body={copy.home.empty.body} />
      )}

      {ready && allPeople.length > 0 && visiblePeople.length === 0 && (
        <EmptyState
          title={copy.home.emptyFiltered.title}
          body={copy.home.emptyFiltered.body}
          action={
            <Button
              onClick={() => {
                showView(clearFilters(view));
              }}
            >
              {copy.home.emptyFiltered.action}
            </Button>
          }
        />
      )}

      {ready && visiblePeople.length > 0 && (
        <PeopleTable people={visiblePeople} clock={clock} vocabulary={vocabulary} />
      )}
    </div>
  );
}
