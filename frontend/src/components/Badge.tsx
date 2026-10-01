import { BADGE_BASE, TONE_CLASSES, type BadgeTone } from './badgeStyles';

export type { BadgeTone } from './badgeStyles';

interface BadgeProps {
  tone: BadgeTone;
  /** The words shown inside the badge. Colour is never the only signal. */
  label: string;
  /** Spoken before the label by a screen reader, e.g. "Status:". */
  description?: string;
}

/** A small coloured chip whose meaning is always readable as text. */
export function Badge({ tone, label, description }: BadgeProps) {
  return (
    <span className={`${BADGE_BASE} ${TONE_CLASSES[tone]}`}>
      {description !== undefined && <span className="sr-only">{description} </span>}
      {label}
    </span>
  );
}
