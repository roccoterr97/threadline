import { useSearchParams } from 'react-router-dom';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { OrganisationFilters } from '../components/OrganisationFilters';
import { OrganisationsTable } from '../components/OrganisationsTable';
import { PeopleCutNotice } from '../components/PeopleCutNotice';
import { RefreshFailedNote } from '../components/RefreshFailedNote';
import { ViewSwitch } from '../components/ViewSwitch';
import * as copy from '../copy/en';
import { categoriesInUse } from '../domain/categories';
import {
  applyOrganisationsView,
  clearOrganisationFilters,
  readOrganisationsView,
  writeOrganisationsView,
  type OrganisationsView,
} from '../domain/organisations';
import { usePageTitle } from '../hooks/usePageTitle';
import { useReadQuery } from '../hooks/useReadQuery';
import { useVocabulary } from '../hooks/useVocabulary';
import { useClock } from '../lib/ClockContext';

/**
 * The organisations page: the same people as the People page, grouped by
 * where they are, so the owner can see where things stand with each
 * organisation as a whole. It reads the one people list the People page
 * reads, so the two can never disagree and nobody hidden shows up here.
 */
export function OrganisationsPage() {
  usePageTitle(copy.organisations.title);
  const clock = useClock();
  const [searchParams, setSearchParams] = useSearchParams();

  const people = useReadQuery({ queryKey: peopleQueryKey, queryFn: fetchPeople });
  const vocabularyState = useVocabulary();

  const allPeople = people.data ?? [];
  const vocabulary = vocabularyState.status === 'ready' ? vocabularyState.vocabulary : null;
  // Until the categories are known no `type` in the address can be trusted, so it reads as "all".
  const typeOptions = vocabulary === null ? [] : categoriesInUse(vocabulary.categories, allPeople);
  const view = readOrganisationsView(searchParams, typeOptions.map((category) => category.key));
  const refreshFailed =
    people.refreshFailed ||
    (vocabularyState.status === 'ready' && vocabularyState.refreshFailed);
  const ready = people.isSuccess && vocabulary !== null;
  const failed = people.isError || vocabularyState.status === 'error';
  const organisations = applyOrganisationsView(allPeople, view);

  const showView = (next: OrganisationsView) => {
    setSearchParams(writeOrganisationsView(next));
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.organisations.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.organisations.subtitle}</p>
      </div>

      <ViewSwitch />

      <RefreshFailedNote show={refreshFailed} />

      <PeopleCutNotice shown={allPeople.length} />

      {vocabulary !== null && (
        <div className="flex flex-col gap-2">
          <OrganisationFilters
            view={view}
            categories={typeOptions}
            statusLabels={vocabulary.statusLabels}
            onChange={showView}
          />
          <p className="text-sm text-ink-muted">{copy.organisations.filterHint}</p>
        </div>
      )}

      {!ready && !failed && <LoadingState label={copy.organisations.loading} />}

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

      {ready && allPeople.length > 0 && organisations.length === 0 && (
        <EmptyState
          title={copy.organisations.emptyFiltered.title}
          body={copy.organisations.emptyFiltered.body}
          action={
            <Button
              onClick={() => {
                showView(clearOrganisationFilters(view));
              }}
            >
              {copy.home.emptyFiltered.action}
            </Button>
          }
        />
      )}

      {ready && organisations.length > 0 && (
        <OrganisationsTable organisations={organisations} clock={clock} />
      )}
    </div>
  );
}
