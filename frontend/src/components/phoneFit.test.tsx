import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { nameReservedCategory } from '../domain/categories';
import { resolveStatusLabels } from '../domain/vocabulary';
import { fixedClock } from '../lib/clock';
import { NOW, sampleCategories, samplePerson } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { BottomNav } from './BottomNav';
import { FilterSelect } from './FilterSelect';
import { HeaderNav } from './HeaderNav';
import { CARD_LINK, TAP_LINK } from './linkStyles';
import { PersonCard } from './PersonCard';
import { SortSelect } from './SortSelect';
import { ViewSwitch } from './ViewSwitch';

/**
 * Class-level guards for what makes the dashboard usable on an iPhone. jsdom
 * cannot lay anything out, so these keep the rules from being dropped by
 * accident; the sizes themselves were checked in a phone-sized browser.
 */

/** iOS Safari zooms into any field set in less than 16px, which is Tailwind's `text-base`. */
const NO_ZOOM_TEXT = 'text-base';
const SMALL_TEXT = 'text-sm';

describe('fields on a phone', () => {
  it('sets the filter list in text big enough that iOS does not zoom in', () => {
    renderWithProviders(
      <FilterSelect
        label="Status"
        value="a"
        options={['a', 'b']}
        labels={{ a: 'A', b: 'B' }}
        onChange={() => undefined}
      />,
    );
    const field = screen.getByRole('combobox', { name: 'Status' });
    expect(field).toHaveClass(NO_ZOOM_TEXT);
    expect(field).not.toHaveClass(SMALL_TEXT);
  });

  it('sets the sort list in text big enough that iOS does not zoom in', () => {
    renderWithProviders(<SortSelect value="name" onChange={() => undefined} />);
    const field = screen.getByRole('combobox', { name: copy.home.sortLabel });
    expect(field).toHaveClass(NO_ZOOM_TEXT);
    expect(field).not.toHaveClass(SMALL_TEXT);
  });
});

describe('links on a phone', () => {
  it('gives a lone text link the height of a button', () => {
    expect(TAP_LINK).toContain('min-h-11');
  });

  it('opens the person from anywhere on the card', () => {
    renderWithProviders(
      <ul>
        <PersonCard
          person={samplePerson()}
          clock={fixedClock(NOW)}
          vocabulary={{
            categories: nameReservedCategory(sampleCategories, copy.values.unknown),
            statusLabels: resolveStatusLabels(undefined, copy.defaultStatusLabels),
          }}
        />
      </ul>,
    );
    expect(screen.getByRole('listitem')).toHaveClass('relative');
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(CARD_LINK).toContain('after:absolute');
    expect(CARD_LINK).toContain('after:inset-0');
    expect(screen.getByRole('link')).toHaveClass('after:absolute', 'after:inset-0');
  });
});

describe('the menu on a phone and a tablet', () => {
  it('hands the menu from the bottom bar to the header at the same width', () => {
    renderWithProviders(
      <>
        <HeaderNav reviewCount={0} />
        <BottomNav reviewCount={0} />
        <ViewSwitch />
      </>,
    );
    const header = screen.getByRole('navigation', { name: copy.nav.headerLabel });
    const bottom = screen.getByRole('navigation', { name: copy.nav.bottomBarLabel });
    const switcher = screen.getByRole('navigation', { name: copy.organisations.switchLabel });
    expect(header).toHaveClass('hidden', 'lg:flex');
    expect(bottom).toHaveClass('lg:hidden');
    expect(switcher).toHaveClass('lg:hidden');
  });
});
