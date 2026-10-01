import type { Ref } from 'react';
import * as copy from '../copy/en';
import { MoveDirection } from '../domain/categorySettings';
import { Button } from './Button';

const actions = copy.categorySettings.actions;

interface CategoryRowActionsProps {
  label: string;
  disabled: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onChange: () => void;
  onMove: (direction: MoveDirection) => void;
  onRemove: () => void;
  /** Lets the row put the keyboard back on one of these buttons. */
  buttonRefs: {
    up: Ref<HTMLButtonElement>;
    down: Ref<HTMLButtonElement>;
    remove: Ref<HTMLButtonElement>;
  };
}

/**
 * Change, move and remove for one category. Every button names the category
 * for screen readers, since the same words repeat on every row.
 */
export function CategoryRowActions({
  label,
  disabled,
  canMoveUp,
  canMoveDown,
  onChange,
  onMove,
  onRemove,
  buttonRefs,
}: CategoryRowActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button aria-label={actions.changeLabel(label)} disabled={disabled} onClick={onChange}>
        {actions.change}
      </Button>
      <Button
        ref={buttonRefs.up}
        aria-label={actions.moveUpLabel(label)}
        disabled={disabled || !canMoveUp}
        onClick={() => {
          onMove(MoveDirection.Up);
        }}
      >
        {actions.moveUp}
      </Button>
      <Button
        ref={buttonRefs.down}
        aria-label={actions.moveDownLabel(label)}
        disabled={disabled || !canMoveDown}
        onClick={() => {
          onMove(MoveDirection.Down);
        }}
      >
        {actions.moveDown}
      </Button>
      <Button
        ref={buttonRefs.remove}
        variant="danger"
        aria-label={actions.removeLabel(label)}
        disabled={disabled}
        onClick={onRemove}
      >
        {actions.remove}
      </Button>
    </div>
  );
}
