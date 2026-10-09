import * as copy from '../copy/en';
import type { OrganisationSummary } from '../domain/organisations';
import type { Clock } from '../lib/clock';
import { formatRelative } from '../lib/format';
import { CARD_LINK } from './linkStyles';
import { OrganisationLink } from './OrganisationLink';
import { OrganisationStateBadges } from './OrganisationStateBadges';

interface OrganisationCardProps {
  organisation: OrganisationSummary;
  clock: Clock;
}

/** One organisation as a stacked card — the phone-width view of a table row. */
export function OrganisationCard({ organisation, clock }: OrganisationCardProps) {
  return (
    <li className="relative rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <OrganisationLink name={organisation.name} className={CARD_LINK} />
      {organisation.name === null && (
        <p className="mt-1 text-sm text-ink-muted">{copy.organisations.noOrganisationHint}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <OrganisationStateBadges organisation={organisation} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <dt className="text-ink-muted">{copy.organisations.columns.people}</dt>
          <dd className="text-ink">{copy.organisations.peopleCount(organisation.people.length)}</dd>
        </div>
        <div>
          <dt className="text-ink-muted">{copy.home.columns.lastContact}</dt>
          <dd className="text-ink">{formatRelative(organisation.lastContactAt, clock)}</dd>
        </div>
      </dl>
    </li>
  );
}
