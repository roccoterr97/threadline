import * as copy from '../copy/en';
import { categoryFor } from '../domain/categories';
import { formatRoleLine } from '../lib/format';
import type { Vocabulary } from '../domain/vocabulary';
import type { PeopleOverviewRow } from '../types/database';
import { Badge } from './Badge';
import { FollowUpBadge } from './FollowUpBadge';
import { PersonTypeBadge } from './PersonTypeBadge';
import { SignalBadge } from './SignalBadge';
import { StatusBadge } from './StatusBadge';
import { WaitingOnBadge } from './WaitingOnBadge';

interface PersonHeaderProps {
  person: PeopleOverviewRow;
  vocabulary: Vocabulary;
}

/** The person's name, role and organisation, with where things stand as badges. */
export function PersonHeader({ person, vocabulary }: PersonHeaderProps) {
  const roleLine = formatRoleLine(person.role_title, person.organisation_name);
  return (
    <div>
      <h1 className="text-2xl font-semibold break-words text-ink">{person.full_name}</h1>
      {roleLine !== null && <p className="mt-1 break-words text-ink-muted">{roleLine}</p>}
      <div
        role="group"
        aria-label={copy.person.stateGroupLabel}
        className="mt-3 flex flex-wrap gap-2"
      >
        <PersonTypeBadge
          category={categoryFor(vocabulary.categories, person.person_type)}
        />
        <StatusBadge status={person.status} labels={vocabulary.statusLabels} />
        <WaitingOnBadge waitingOn={person.waiting_on} />
        <SignalBadge signal={person.signal} />
        <FollowUpBadge person={person} />
        {person.has_override && <Badge tone="calm" label={copy.person.correctedByYou} />}
      </div>
    </div>
  );
}
