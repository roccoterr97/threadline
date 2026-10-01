import { describe, expect, it } from 'vitest';
import {
  category,
  salesCategories,
  sampleCategories,
  withArchived,
} from '../test/__fixtures__/sampleData';
import type { CategorySuggestion } from '../types/database';
import {
  activeOwnCategories,
  canAddCategory,
  categoryKeyFromName,
  DraftProblem,
  findDraftProblem,
  firstFreeColour,
  hiddenCategories,
  moveCategory,
  MoveDirection,
  nextSortOrder,
  suggestedGroupLabel,
  suggestionsToOffer,
} from './categorySettings';

const HUES = ['violet', 'cyan', 'orange', 'pink', 'indigo', 'teal', 'olive', 'brown'] as const;

/** Eight of the owner's own categories, one per hue, plus the reserved one: the most allowed. */
const FULL = [
  ...HUES.map((hue, index) => category(`cat_${hue}`, hue, `${hue}s`, hue, (index + 1) * 10)),
  category('unknown', 'Not known', 'Unknown', 'grey', 1000),
];

describe('categoryKeyFromName', () => {
  it.each([
    ['Customer', 'customer'],
    ['  Key accounts  ', 'key_accounts'],
    ['Friends & family!', 'friends_family'],
    ['Café owners', 'cafe_owners'],
    ['2nd degree', 'c_2nd_degree'],
    ['!!!', 'c'],
    ['A'.repeat(50), 'a'.repeat(31)],
  ])('turns %j into %j', (name, key) => {
    expect(categoryKeyFromName(name, [])).toBe(key);
  });

  it('never gives a reserved key', () => {
    expect(categoryKeyFromName('All', [])).toBe('all_2');
    expect(categoryKeyFromName('Unknown', [])).toBe('unknown_2');
  });

  it('numbers a clash with an existing key', () => {
    expect(categoryKeyFromName('Customer', ['customer'])).toBe('customer_2');
    expect(categoryKeyFromName('Customer', ['customer', 'customer_2'])).toBe('customer_3');
  });

  it('keeps a numbered key within 31 characters', () => {
    const long = 'b'.repeat(31);
    const key = categoryKeyFromName(long, [long]);
    expect(key).toBe(`${'b'.repeat(29)}_2`);
    expect(key).toMatch(/^[a-z][a-z0-9_]{0,30}$/);
  });
});

describe('the lists on the settings page', () => {
  it('splits the owner\'s categories in use from the hidden ones, leaving "not known" out', () => {
    const categories = withArchived(sampleCategories, 'network');
    expect(activeOwnCategories(categories).map((c) => c.key)).toEqual(['startup', 'vc']);
    expect(hiddenCategories(categories).map((c) => c.key)).toEqual(['network']);
  });

  it('allows adding until eight categories are in use', () => {
    expect(canAddCategory(sampleCategories)).toBe(true);
    expect(canAddCategory(FULL)).toBe(false);
    expect(canAddCategory(withArchived(FULL, 'cat_violet'))).toBe(true);
  });

  it('puts a new category after every other one of the owner\'s', () => {
    expect(nextSortOrder(sampleCategories)).toBe(40);
    expect(nextSortOrder(salesCategories.filter((c) => c.key === 'unknown'))).toBe(10);
  });

  it('offers only suggestions that are not already a category, hidden ones included', () => {
    const suggestion = (key: string): CategorySuggestion => ({
      key,
      label: key,
      group_label: key,
      description: 'Someone.',
      colour: 'teal',
    });
    const offered = suggestionsToOffer(
      [suggestion('startup'), suggestion('network'), suggestion('mentor')],
      withArchived(sampleCategories, 'network'),
    );
    expect(offered.map((s) => s.key)).toEqual(['mentor']);
  });

  it('picks the first colour nobody uses yet', () => {
    expect(firstFreeColour(sampleCategories)).toBe('pink');
    expect(firstFreeColour(FULL)).toBe('grey');
  });
});

describe('moveCategory', () => {
  it('swaps a category with the one above and numbers the list 10, 20, 30…', () => {
    const categories = sampleCategories.map((c) =>
      c.key === 'unknown' ? c : { ...c, sort_order: c.sort_order + 5 },
    );
    expect(moveCategory(categories, 'vc', MoveDirection.Up)).toEqual([
      { key: 'vc', sort_order: 10 },
      { key: 'startup', sort_order: 20 },
      { key: 'network', sort_order: 30 },
    ]);
  });

  it('sends only the positions that changed', () => {
    expect(moveCategory(sampleCategories, 'vc', MoveDirection.Down)).toEqual([
      { key: 'network', sort_order: 20 },
      { key: 'vc', sort_order: 30 },
    ]);
  });

  it('does nothing at either end, or for "not known"', () => {
    expect(moveCategory(sampleCategories, 'startup', MoveDirection.Up)).toEqual([]);
    expect(moveCategory(sampleCategories, 'network', MoveDirection.Down)).toEqual([]);
    expect(moveCategory(sampleCategories, 'unknown', MoveDirection.Up)).toEqual([]);
  });
});

describe('drafts', () => {
  const good = {
    label: 'Customer',
    group_label: 'Customers',
    description: 'Buys from us.',
    colour: 'teal',
  } as const;

  it('suggests a group name from the name', () => {
    expect(suggestedGroupLabel(' Customer ')).toBe('Customers');
    expect(suggestedGroupLabel('  ')).toBe('');
  });

  it.each([
    [{ label: '   ' }, DraftProblem.MissingName],
    [{ label: 'x'.repeat(41) }, DraftProblem.NameTooLong],
    [{ group_label: '' }, DraftProblem.MissingGroupName],
    [{ group_label: 'x'.repeat(41) }, DraftProblem.GroupNameTooLong],
    [{ description: ' ' }, DraftProblem.MissingDescription],
    [{ description: 'x'.repeat(1001) }, DraftProblem.DescriptionTooLong],
  ])('finds the problem in %o', (change, problem) => {
    expect(findDraftProblem({ ...good, ...change })).toBe(problem);
  });

  it('accepts a complete draft', () => {
    expect(findDraftProblem(good)).toBeNull();
  });
});
