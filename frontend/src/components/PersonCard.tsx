import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import { categoryFor } from '../domain/categories';
import type { Vocabulary } from '../domain/vocabulary';
import type { Clock } from '../lib/clock';
import { formatDate, formatRelative } from '../lib/format';
import type { PeopleOverviewRow } from '../types/database';
import { FollowUpBadge } from './FollowUpBadge';
import { PersonTypeBadge } from './PersonTypeBadge';
import { SignalBadge } from './SignalBadge';
import { StatusBadge } from './StatusBadge';
import { WaitingOnBadge } from './WaitingOnBadge';

interface PersonCardProps {
  person: PeopleOverviewRow;
  clock: Clock;
  vocabulary: Vocabulary;
}

/** One person as a stacked card — the phone-width view of a table row. */
export function PersonCard({ person, clock, vocabulary }: PersonCardProps) {
  return (
    <li className="rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <Link
        to={`/people/${person.person_id}`}
        className="text-lg font-semibold text-accent underline underline-offset-2"
      >
        {person.full_name}
      </Link>
      <p className="mt-1 text-sm text-ink-muted">
        {person.role_title ?? copy.values.unknown}
        {person.organisation_name !== null && ` · ${person.organisation_name}`}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <PersonTypeBadge
          category={categoryFor(vocabulary.categories, person.person_type)}
        />
        <StatusBadge status={person.status} labels={vocabulary.statusLabels} />
        <WaitingOnBadge waitingOn={person.waiting_on} />
        <SignalBadge signal={person.signal} />
        <FollowUpBadge person={person} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <dt className="text-ink-muted">{copy.home.columns.lastContact}</dt>
          <dd className="text-ink">{formatRelative(person.last_contact_at, clock)}</dd>
        </div>
        <div>
          <dt className="text-ink-muted">{copy.home.columns.due}</dt>
          <dd className="text-ink">{formatDate(person.due_date)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-ink-muted">{copy.home.columns.nextAction}</dt>
          <dd className="text-ink">{person.next_action ?? copy.values.none}</dd>
        </div>
      </dl>
    </li>
  );
}
