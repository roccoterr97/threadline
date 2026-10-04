import * as copy from '../copy/en';
import { isAssessed, type OrganisationSummary } from '../domain/organisations';
import { Badge, type BadgeTone } from './Badge';
import { WAITING_TONES } from './badgeStyles';
import { WaitingOnBadge } from './WaitingOnBadge';

interface OrganisationStateBadgesProps {
  organisation: OrganisationSummary;
}

/** One number of the picture: which counter, in which words and colour. */
interface StateCount {
  key: 'overdue' | 'actionsForMe' | 'timeToChase' | 'waitingOnThem';
  label: string;
  tone: BadgeTone;
}

/**
 * Most pressing first, in the same words and colours the people rows use:
 * a late reply is red, the owner's turn amber, a nudge grey, their turn plain.
 */
const STATE_COUNTS: readonly StateCount[] = [
  { key: 'overdue', label: copy.dueBadgeLabels.overdue, tone: 'danger' },
  { key: 'actionsForMe', label: copy.waitingOnBadges.me, tone: WAITING_TONES.me },
  { key: 'timeToChase', label: copy.dueBadgeLabels.chase, tone: 'neutral' },
  { key: 'waitingOnThem', label: copy.waitingOnBadges.them, tone: WAITING_TONES.them },
];

/**
 * The compact picture of where things stand with an organisation: how many
 * people there are waiting on the owner, overdue, due a nudge, or waited on.
 * Shows only the numbers above zero; when none is, it says who is waiting the
 * way a person's row does.
 */
export function OrganisationStateBadges({ organisation }: OrganisationStateBadgesProps) {
  const shown = STATE_COUNTS.filter((count) => organisation.counters[count.key] > 0);
  if (shown.length === 0) {
    return <WaitingOnBadge waitingOn={isAssessed(organisation) ? 'nobody' : null} />;
  }
  return (
    <>
      {shown.map((count) => (
        <Badge
          key={count.key}
          tone={count.tone}
          label={copy.organisations.stateCount(count.label, organisation.counters[count.key])}
        />
      ))}
    </>
  );
}
