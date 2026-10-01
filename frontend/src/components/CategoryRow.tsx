import { useEffect, useRef, useState } from 'react';
import * as copy from '../copy/en';
import { MoveDirection } from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category } from '../types/database';
import { CategoryEditForm } from './CategoryEditForm';
import { CategoryRowActions } from './CategoryRowActions';
import { ConfirmPanel } from './ConfirmPanel';
import { TypeDot } from './TypeDot';

const actions = copy.categorySettings.actions;

interface CategoryRowProps {
  category: Category;
  /** Every other category, hidden ones included. */
  others: readonly Category[];
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (direction: MoveDirection) => void;
  /** Set on the row just moved: which of its move buttons gets the keyboard back. */
  focusAfterMove: MoveDirection | null;
  onMoveFocused: () => void;
  editor: CategoryEditor;
}

type Mode = 'view' | 'editing' | 'confirming-removal';

/**
 * One of the owner's categories: its colour, names and description, with
 * buttons to change, move or remove it. Removing asks first, because a
 * category people still have is hidden rather than removed.
 */
export function CategoryRow({
  category,
  others,
  canMoveUp,
  canMoveDown,
  onMove,
  focusAfterMove,
  onMoveFocused,
  editor,
}: CategoryRowProps) {
  const [mode, setMode] = useState<Mode>('view');
  const buttons = {
    up: useRef<HTMLButtonElement>(null),
    down: useRef<HTMLButtonElement>(null),
    remove: useRef<HTMLButtonElement>(null),
  };
  const refocusRemove = useRef(false);
  const { key, label } = category;

  // Once the move has ended and the list is in its new order, the keyboard
  // goes back to the button just used, or to the other one if the row has
  // reached that end of the list.
  useEffect(() => {
    if (focusAfterMove === null) return;
    const sameWayOpen = focusAfterMove === MoveDirection.Up ? canMoveUp : canMoveDown;
    const goesUp = (focusAfterMove === MoveDirection.Up) === sameWayOpen;
    (goesUp ? buttons.up : buttons.down).current?.focus();
    onMoveFocused();
  }, [focusAfterMove, canMoveUp, canMoveDown, buttons.up, buttons.down, onMoveFocused]);

  useEffect(() => {
    if (mode !== 'view' || !refocusRemove.current) return;
    refocusRemove.current = false;
    buttons.remove.current?.focus();
  }, [mode, buttons.remove]);

  return (
    <li className="flex flex-col gap-3 rounded-token-lg border border-line bg-surface p-4">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 font-semibold text-ink">
          <TypeDot colour={category.colour} />
          {label} <span className="font-normal text-ink-muted">· {category.group_label}</span>
        </p>
        {category.description !== '' && (
          <p className="text-sm break-words text-ink-muted">{category.description}</p>
        )}
      </div>

      {mode === 'editing' && (
        <CategoryEditForm
          category={category}
          others={others}
          isBusy={editor.isBusy}
          onCancel={() => {
            setMode('view');
          }}
          onSave={(draft) => {
            const action = { kind: 'update', key, label: draft.label, changes: draft } as const;
            editor.run(action, {
              onSaved: () => {
                setMode('view');
              },
            });
          }}
        />
      )}

      {mode === 'confirming-removal' && (
        <ConfirmPanel
          title={actions.removeConfirmTitle(label)}
          body={actions.removeConfirmBody}
          confirmLabel={actions.removeConfirm}
          cancelLabel={actions.removeCancel}
          isBusy={editor.isBusy}
          errorText={null}
          onConfirm={() => {
            editor.run({ kind: 'remove', key, label });
          }}
          onCancel={() => {
            refocusRemove.current = true;
            setMode('view');
          }}
        />
      )}

      {mode === 'view' && (
        <CategoryRowActions
          label={label}
          disabled={editor.isBusy}
          canMoveUp={canMoveUp}
          canMoveDown={canMoveDown}
          onChange={() => {
            setMode('editing');
          }}
          onMove={onMove}
          onRemove={() => {
            setMode('confirming-removal');
          }}
          buttonRefs={buttons}
        />
      )}
    </li>
  );
}
