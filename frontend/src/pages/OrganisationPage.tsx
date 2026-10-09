import { Link, useLocation, useParams } from 'react-router-dom';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { EmptyState } from '../components/EmptyState';
import { TAP_LINK } from '../components/linkStyles';
import { ErrorState } from '../components/ErrorState';
import { HiddenPersonNotice } from '../components/HiddenPersonNotice';
import { LoadingState } from '../components/LoadingState';
import { OrganisationStateBadges } from '../components/OrganisationStateBadges';
import { PeopleCutNotice } from '../components/PeopleCutNotice';
import { PeopleTable } from '../components/PeopleTable';
import { RefreshFailedNote } from '../components/RefreshFailedNote';
import * as copy from '../copy/en';
import { findOrganisation, type OrganisationSummary } from '../domain/organisations';
import { usePageTitle } from '../hooks/usePageTitle';
import { useReadQuery } from '../hooks/useReadQuery';
import { useVocabulary } from '../hooks/useVocabulary';
import { useClock } from '../lib/ClockContext';
import { formatRelative } from '../lib/format';
import { organisationsListAddress } from '../lib/organisationAddress';
import type { Clock } from '../lib/clock';

/** The name, how many people are there, and the picture of where things stand. */
function OrganisationHeader({
  organisation,
  clock,
}: {
  organisation: OrganisationSummary;
  clock: Clock;
}) {
  const lastContact = formatRelative(organisation.lastContactAt, clock);
  return (
    <div>
      <h1 className="text-2xl font-semibold break-words text-ink">
        {organisation.name ?? copy.organisations.noOrganisation}
      </h1>
      <p className="mt-1 text-ink-muted">
        {organisation.name === null && `${copy.organisations.noOrganisationHint} `}
        {copy.organisations.inTouch(organisation.people.length)}{' '}
        {`${copy.home.columns.lastContact}: ${lastContact}.`}
      </p>
      <div
        role="group"
        aria-label={copy.organisations.stateGroupLabel}
        className="mt-3 flex flex-wrap gap-2"
      >
        <OrganisationStateBadges organisation={organisation} />
      </div>
    </div>
  );
}

/**
 * One organisation: the people the owner is in touch with there, in the same
 * rows as the People page, each opening the person. Everything comes from the
 * one people list the dashboard already reads. The way back to the list keeps
 * the filters and order it was opened with.
 */
export function OrganisationPage() {
  const clock = useClock();
  const { organisationName = null } = useParams<{ organisationName: string }>();
  const listAddress = organisationsListAddress(useLocation().state);

  const people = useReadQuery({ queryKey: peopleQueryKey, queryFn: fetchPeople });
  const vocabulary = useVocabulary();
  const organisation = people.isSuccess ? findOrganisation(people.data, organisationName) : null;
  usePageTitle(
    people.isSuccess
      ? (organisation?.name ?? copy.organisations.noOrganisation)
      : null,
  );

  const backLink = (
    <Link to={listAddress} className={`self-start ${TAP_LINK}`}>
      {copy.organisations.backToOrganisations}
    </Link>
  );

  if (people.isError) {
    return (
      <ErrorState
        error={people.error}
        onRetry={() => {
          void people.refetch();
        }}
      />
    );
  }

  if (vocabulary.status === 'error') {
    return <ErrorState error={vocabulary.error} onRetry={vocabulary.retry} />;
  }

  if (people.isPending || vocabulary.status === 'pending') {
    return <LoadingState label={copy.organisations.loading} />;
  }

  if (organisation === null) {
    return (
      <div className="flex flex-col gap-6">
        <HiddenPersonNotice />
        <EmptyState
          title={copy.organisations.notFound.title}
          body={copy.organisations.notFound.body}
          action={backLink}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {backLink}
      <OrganisationHeader organisation={organisation} clock={clock} />
      <HiddenPersonNotice />
      <RefreshFailedNote show={people.refreshFailed || vocabulary.refreshFailed} />
      <PeopleCutNotice shown={people.data.length} />
      <PeopleTable people={organisation.people} clock={clock} vocabulary={vocabulary.vocabulary} />
    </div>
  );
}
