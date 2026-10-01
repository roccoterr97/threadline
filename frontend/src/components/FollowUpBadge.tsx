import * as copy from '../copy/en';
import type { PeopleOverviewRow } from '../types/database';
import { Badge } from './Badge';

interface FollowUpBadgeProps {
  person: Pick<PeopleOverviewRow, 'is_overdue' | 'is_chase_due'>;
}

/**
 * Flags a follow-up whose date has passed.
 *
 * A reply the owner owes is red; a nudge the owner could send is calm and
 * neutral, because nothing is wrong on the owner's side. Shows nothing when neither applies.
 */
export function FollowUpBadge({ person }: FollowUpBadgeProps) {
  if (person.is_overdue) {
    return (
      <Badge
        tone="danger"
        label={copy.dueBadgeLabels.overdue}
        description={copy.dueBadgeLabels.description}
      />
    );
  }
  if (person.is_chase_due) {
    return (
      <Badge
        tone="neutral"
        label={copy.dueBadgeLabels.chase}
        description={copy.dueBadgeLabels.description}
      />
    );
  }
  return null;
}
