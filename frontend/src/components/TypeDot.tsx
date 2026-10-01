import type { CategoryColour } from '../types/database';
import { CATEGORY_DOT_CLASSES } from './badgeStyles';

interface TypeDotProps {
  colour: CategoryColour;
}

/**
 * A small dot in a category's palette colour. Decorative: it always sits next
 * to the category's name, so screen readers skip it.
 */
export function TypeDot({ colour }: TypeDotProps) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-2.5 shrink-0 rounded-full ring-2 ring-surface ${CATEGORY_DOT_CLASSES[colour]}`}
    />
  );
}
