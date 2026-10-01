import { describe, expect, it } from 'vitest';
import {
  sampleCategories,
  samplePeople,
  singleCategory,
  withArchived,
} from '../test/__fixtures__/sampleData';
import type { Category } from '../types/database';
import { categoriesInUse, categoryChoices, categoryFor, isArchived } from './categories';

/** The sample preset with `network` retired. */
const withNetworkArchived = withArchived(sampleCategories, 'network');

function keys(categories: readonly Category[]): string[] {
  return categories.map((category) => category.key);
}

describe('categoryFor', () => {
  it('finds a category by its key', () => {
    expect(categoryFor(sampleCategories, 'vc')).toMatchObject({ label: 'Investor', colour: 'cyan' });
  });

  it('still finds an archived category, so people who have it keep its name and colour', () => {
    expect(categoryFor(withNetworkArchived, 'network')).toMatchObject({
      label: 'Network',
      colour: 'orange',
    });
  });

  it('shows a key the list does not know as itself, in grey', () => {
    expect(categoryFor(sampleCategories, 'mystery')).toMatchObject({
      key: 'mystery',
      label: 'mystery',
      group_label: 'mystery',
      colour: 'grey',
    });
  });
});

describe('categoriesInUse', () => {
  it('shows every live category in list order, even with nobody in it', () => {
    expect(keys(categoriesInUse(sampleCategories, []))).toEqual([
      'startup',
      'vc',
      'network',
      'unknown',
    ]);
  });

  it('works with just one category of its own', () => {
    expect(keys(categoriesInUse(singleCategory, []))).toEqual(['member', 'unknown']);
  });

  it('shows an archived category only while someone still has it', () => {
    expect(keys(categoriesInUse(withNetworkArchived, samplePeople))).toContain('network');
    const nobodyInNetwork = samplePeople.filter((person) => person.person_type !== 'network');
    expect(keys(categoriesInUse(withNetworkArchived, nobodyInNetwork))).not.toContain('network');
  });

  it('adds a key the list does not know after the rest, while someone has it', () => {
    const stray = { ...samplePeople[0]!, person_type: 'mystery' };
    const shown = categoriesInUse(sampleCategories, [stray]);
    expect(keys(shown)).toEqual(['startup', 'vc', 'network', 'unknown', 'mystery']);
    expect(shown.at(-1)?.colour).toBe('grey');
  });
});

describe('categoryChoices', () => {
  it('offers every live category and never an archived one', () => {
    const choices = categoryChoices(withNetworkArchived, null);
    expect(keys(choices)).toEqual(['startup', 'vc', 'unknown']);
    expect(choices.some(isArchived)).toBe(false);
  });

  it('keeps the saved value as a choice even after it was archived', () => {
    expect(keys(categoryChoices(withNetworkArchived, 'network'))).toEqual([
      'startup',
      'vc',
      'unknown',
      'network',
    ]);
  });

  it('does not repeat a saved value that is still live', () => {
    expect(keys(categoryChoices(sampleCategories, 'vc'))).toEqual(keys(sampleCategories));
  });
});
