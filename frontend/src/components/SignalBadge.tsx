import * as copy from '../copy/en';
import type { Signal } from '../types/database';
import { Badge } from './Badge';
import { SIGNAL_TONES } from './badgeStyles';

interface SignalBadgeProps {
  signal: Signal | null;
}

/** How warm the conversation feels. */
export function SignalBadge({ signal }: SignalBadgeProps) {
  if (signal === null) {
    return <Badge tone="neutral" label={copy.values.notAssessed} description="Signal:" />;
  }
  return (
    <Badge tone={SIGNAL_TONES[signal]} label={copy.signalLabels[signal]} description="Signal:" />
  );
}
