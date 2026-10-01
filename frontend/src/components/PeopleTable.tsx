import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { Clock } from '../lib/clock';
import { categoryFor } from '../domain/categories';
import type { Vocabulary } from '../domain/vocabulary';
import { formatDate, formatRelative, formatRoleLine } from '../lib/format';
import type { PeopleOverviewRow } from '../types/database';
import { FollowUpBadge } from './FollowUpBadge';
import { PersonCard } from './PersonCard';
import { PersonTypeBadge } from './PersonTypeBadge';
import { SignalBadge } from './SignalBadge';
import { StatusBadge } from './StatusBadge';
import { WaitingOnBadge } from './WaitingOnBadge';

interface PeopleTableProps {
  people: readonly PeopleOverviewRow[];
  clock: Clock;
  vocabulary: Vocabulary;
}

const CELL = 'px-3 py-3 align-top text-sm';

/**
 * The people list.
 *
 * Narrow screens get stacked cards and wide screens get a real table; only one
 * of the two is in the page at a time, so a screen reader never hears both.
 */
export function PeopleTable({ people, clock, vocabulary }: PeopleTableProps) {
  return (
    <>
      <ul className="flex list-none flex-col gap-3 p-0 lg:hidden">
        {people.map((person) => (
          <PersonCard
            key={person.person_id}
            person={person}
            clock={clock}
            vocabulary={vocabulary}
          />
        ))}
      </ul>

      <div className="hidden overflow-x-auto rounded-token-lg border border-line bg-surface lg:block">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">{copy.home.tableCaption}</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.person}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.type}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.lastContact}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.status}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.waitingOn}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.nextAction}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.due}
              </th>
              <th scope="col" className={`${CELL} font-semibold`}>
                {copy.home.columns.signal}
              </th>
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.person_id} className="border-b border-line last:border-b-0">
                <th scope="row" className={`${CELL} font-normal`}>
                  <Link
                    to={`/people/${person.person_id}`}
                    className="font-medium text-accent underline underline-offset-2"
                  >
                    {person.full_name}
                  </Link>
                  <span className="block text-ink-muted">
                    {formatRoleLine(person.role_title, person.organisation_name)}
                  </span>
                </th>
                <td className={CELL}>
                  <PersonTypeBadge
                    category={categoryFor(vocabulary.categories, person.person_type)}
                  />
                </td>
                <td className={CELL}>{formatRelative(person.last_contact_at, clock)}</td>
                <td className={CELL}>
                  <StatusBadge status={person.status} labels={vocabulary.statusLabels} />
                </td>
                <td className={CELL}>
                  <WaitingOnBadge waitingOn={person.waiting_on} />
                </td>
                <td className={CELL}>{person.next_action ?? copy.values.none}</td>
                <td className={CELL}>
                  <span className="flex flex-col gap-1">
                    <span>{formatDate(person.due_date)}</span>
                    <FollowUpBadge person={person} />
                  </span>
                </td>
                <td className={CELL}>
                  <SignalBadge signal={person.signal} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
