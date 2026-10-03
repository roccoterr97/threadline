import { useState } from 'react';
import * as copy from '../copy/en';
import {
  activeOwnCategories,
  isReserved,
  moveCategory,
  type MoveDirection,
} from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category } from '../types/database';
import { CategoryRow } from './CategoryRow';
import { SettingsSection } from './SettingsSection';
import { TypeDot } from './TypeDot';

interface CategoryListProps {
  categories: readonly Category[];
  editor: CategoryEditor;
}

/** The reserved "not known" category: shown so the list is complete, never editable. */
function ReservedCategoryRow({ category }: { category: Category }) {
  return (
    <li className="flex flex-col gap-1 rounded-token-lg border border-dashed border-line-strong p-4">
      <p className="flex items-center gap-2 font-semibold text-ink">
        <TypeDot colour={category.colour} />
        {category.label}
      </p>
      <p className="text-sm text-ink-muted">{copy.categorySettings.reservedNote}</p>
    </li>
  );
}

/**
 * "Your categories": the ones in use, in the order the dashboard shows them,
 * with "not known" always last and fixed in place.
 */
export function CategoryList({ categories, editor }: CategoryListProps) {
  const own = activeOwnCategories(categories);
  const reserved = categories.find(isReserved);
  // The row just moved, set once the new order is in so it can take the keyboard back.
  // Only a move that worked: after a failure the keyboard belongs to the message.
  const [lastMove, setLastMove] = useState<{ key: string; direction: MoveDirection } | null>(
    null,
  );

  const move = (category: Category, direction: MoveDirection) => {
    const changes = moveCategory(categories, category.key, direction);
    if (changes.length === 0) return;
    editor.run(
      { kind: 'move', label: category.label, changes },
      {
        onSaved: () => {
          setLastMove({ key: category.key, direction });
        },
      },
    );
  };

  return (
    <SettingsSection title={copy.categorySettings.yours}>
      {own.length === 0 && <p className="text-ink-muted">{copy.categorySettings.none}</p>}
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {own.map((category, index) => (
          <CategoryRow
            key={category.key}
            category={category}
            others={categories.filter((other) => other.key !== category.key)}
            canMoveUp={index > 0}
            canMoveDown={index < own.length - 1}
            onMove={(direction) => {
              move(category, direction);
            }}
            focusAfterMove={lastMove?.key === category.key ? lastMove.direction : null}
            onMoveFocused={() => {
              setLastMove(null);
            }}
            editor={editor}
          />
        ))}
        {reserved !== undefined && <ReservedCategoryRow category={reserved} />}
      </ol>
    </SettingsSection>
  );
}
