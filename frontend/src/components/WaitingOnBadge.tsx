import * as copy from '../copy/en';
import type { WaitingOn } from '../types/database';
import { Badge } from './Badge';
import { WAITING_TONES } from './badgeStyles';

interface WaitingOnBadgeProps {
  waitingOn: WaitingOn | null;
}

/** Who owes the next message, in words that make sense without a column heading. */
export function WaitingOnBadge({ waitingOn }: WaitingOnBadgeProps) {
  if (waitingOn === null) {
    return <Badge tone="neutral" label={copy.values.notAssessed} description="Waiting on:" />;
  }
  return <Badge tone={WAITING_TONES[waitingOn]} label={copy.waitingOnBadges[waitingOn]} />;
}
