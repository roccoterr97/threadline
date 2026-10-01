import * as copy from '../copy/en';
import type { StatusLabels } from '../domain/vocabulary';
import type { ContactStatus } from '../types/database';
import { Badge } from './Badge';
import { STATUS_TONES } from './badgeStyles';

interface StatusBadgeProps {
  status: ContactStatus | null;
  labels: StatusLabels;
}

/** Where a conversation stands, as words plus a supporting colour. */
export function StatusBadge({ status, labels }: StatusBadgeProps) {
  if (status === null) {
    return <Badge tone="neutral" label={copy.values.notAssessed} description="Status:" />;
  }
  return <Badge tone={STATUS_TONES[status]} label={labels[status]} description="Status:" />;
}
