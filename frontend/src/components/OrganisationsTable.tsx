import * as copy from '../copy/en';
import type { OrganisationSummary } from '../domain/organisations';
import type { Clock } from '../lib/clock';
import { formatRelative } from '../lib/format';
import { OrganisationCard } from './OrganisationCard';
import { OrganisationLink } from './OrganisationLink';
import { OrganisationStateBadges } from './OrganisationStateBadges';

interface OrganisationsTableProps {
  organisations: readonly OrganisationSummary[];
  clock: Clock;
}

const CELL = 'px-3 py-3 align-top text-sm';

/** The key of one row: a name, or the one group without. */
function rowKey(organisation: OrganisationSummary): string {
  return organisation.name ?? '';
}

/**
 * The organisations list.
 *
 * Narrow screens get stacked cards and wide screens get a real table; only one
 * of the two is in the page at a time, so a screen reader never hears both.
 */
export function OrganisationsTable({ organisations, clock }: OrganisationsTableProps) {
  return (
    <>
      <ul className="flex list-none flex-col gap-3 p-0 lg:hidden">
        {organisations.map((organisation) => (
          <OrganisationCard key={rowKey(organisation)} organisation={organisation} clock={clock} />
        ))}
      </ul>

      <div className="hidden overflow-x-auto rounded-token-lg border border-line bg-surface lg:block">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">{copy.organisations.tableCaption}</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.organisation}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.organisations.columns.people}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.organisations.columns.state}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.lastContact}
              </th>
            </tr>
          </thead>
          <tbody>
            {organisations.map((organisation) => (
              <tr key={rowKey(organisation)} className="border-b border-line last:border-b-0">
                <th scope="row" className={`${CELL} font-normal`}>
                  <OrganisationLink
                    name={organisation.name}
                    className="font-medium text-accent underline underline-offset-2"
                  />
                  {organisation.name === null && (
                    <span className="block text-ink-muted">
                      {copy.organisations.noOrganisationHint}
                    </span>
                  )}
                </th>
                <td className={`${CELL} tabular-nums`}>
                  {copy.organisations.peopleCount(organisation.people.length)}
                </td>
                <td className={CELL}>
                  <span className="flex flex-wrap gap-2">
                    <OrganisationStateBadges organisation={organisation} />
                  </span>
                </td>
                <td className={CELL}>{formatRelative(organisation.lastContactAt, clock)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
