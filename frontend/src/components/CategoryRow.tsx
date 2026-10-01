import { useState } from 'react';
import * as copy from '../copy/en';
import { MoveDirection } from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category } from '../types/database';
import { Button } from './Button';
import { CategoryEditForm } from './CategoryEditForm';
import { TypeDot } from './TypeDot';

const actions = copy.categorySettings.actions;

interface CategoryRowProps {
  category: Category;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (direction: MoveDirection) => void;
  editor: CategoryEditor;
}

/**
 * One of the owner's categories: its colour, names and description, with
 * buttons to change, move or remove it. Every button names the category for
 * screen readers, since the same words repeat on every row.
 */
export function CategoryRow({
  category,
  canMoveUp,
  canMoveDown,
  onMove,
  editor,
}: CategoryRowProps) {
  const [editing, setEditing] = useState(false);
  const { label } = category;

  return (
    <li className="flex flex-col gap-3 rounded-token-lg border border-line bg-surface p-4">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 font-semibold text-ink">
          <TypeDot colour={category.colour} />
          {label}{' '}
          <span className="font-normal text-ink-muted">· {category.group_label}</span>
        </p>
        {category.description !== '' && (
          <p className="text-sm break-words text-ink-muted">{category.description}</p>
        )}
      </div>

      {editing ? (
        <CategoryEditForm
          category={category}
          isBusy={editor.isBusy}
          onCancel={() => {
            setEditing(false);
          }}
          onSave={(draft) => {
            const { key } = category;
            editor.run({ kind: 'update', key, label: draft.label, changes: draft }, () => {
              setEditing(false);
            });
          }}
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button
            aria-label={actions.changeLabel(label)}
            disabled={editor.isBusy}
            onClick={() => {
              setEditing(true);
            }}
          >
            {actions.change}
          </Button>
          <Button
            aria-label={actions.moveUpLabel(label)}
            disabled={editor.isBusy || !canMoveUp}
            onClick={() => {
              onMove(MoveDirection.Up);
            }}
          >
            {actions.moveUp}
          </Button>
          <Button
            aria-label={actions.moveDownLabel(label)}
            disabled={editor.isBusy || !canMoveDown}
            onClick={() => {
              onMove(MoveDirection.Down);
            }}
          >
            {actions.moveDown}
          </Button>
          <Button
            variant="danger"
            aria-label={actions.removeLabel(label)}
            disabled={editor.isBusy}
            onClick={() => {
              editor.run({ kind: 'remove', key: category.key, label });
            }}
          >
            {actions.remove}
          </Button>
        </div>
      )}
    </li>
  );
}
