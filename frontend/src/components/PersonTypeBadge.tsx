import * as copy from '../copy/en';
import type { Category } from '../types/database';
import { BADGE_BASE, CATEGORY_BADGE_CLASSES } from './badgeStyles';

interface PersonTypeBadgeProps {
  category: Category;
}

/** The person's category, in its palette colour and always with its name. */
export function PersonTypeBadge({ category }: PersonTypeBadgeProps) {
  return (
    <span className={`${BADGE_BASE} ${CATEGORY_BADGE_CLASSES[category.colour]}`}>
      <span className="sr-only">{copy.home.filtersLabel}: </span>
      {category.label}
    </span>
  );
}
