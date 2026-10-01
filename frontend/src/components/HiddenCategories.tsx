import * as copy from '../copy/en';
import { canAddCategory, hiddenCategories } from '../domain/categorySettings';
import type { CategoryEditor } from '../hooks/useCategoryEditor';
import type { Category } from '../types/database';
import { Button } from './Button';
import { LimitNote } from './LimitNote';
import { SettingsSection } from './SettingsSection';
import { TypeDot } from './TypeDot';

interface HiddenCategoriesProps {
  categories: readonly Category[];
  editor: CategoryEditor;
}

/** Categories the owner hid, each of which can be brought back. Absent when there are none. */
export function HiddenCategories({ categories, editor }: HiddenCategoriesProps) {
  const hidden = hiddenCategories(categories);
  if (hidden.length === 0) return null;
  const canShow = canAddCategory(categories);
  const actions = copy.categorySettings.actions;

  return (
    <SettingsSection title={copy.categorySettings.hidden} intro={copy.categorySettings.hiddenIntro}>
      {!canShow && <LimitNote />}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {hidden.map((category) => (
          <li
            key={category.key}
            className="flex flex-wrap items-center justify-between gap-2 rounded-token-lg border border-line bg-surface p-3"
          >
            <span className="flex items-center gap-2 text-ink">
              <TypeDot colour={category.colour} />
              {category.label}
            </span>
            <Button
              aria-label={actions.showAgainLabel(category.label)}
              disabled={editor.isBusy || !canShow}
              onClick={() => {
                editor.run({ kind: 'show-again', key: category.key, label: category.label });
              }}
            >
              {actions.showAgain}
            </Button>
          </li>
        ))}
      </ul>
    </SettingsSection>
  );
}
