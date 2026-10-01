import { describe, expect, it, vi } from 'vitest';
import { UnexpectedDataError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import { sampleCategories } from '../test/__fixtures__/sampleData';
import { categoryListSchema, fetchCategories } from './categories';
import { statusLabelListSchema } from './statusLabels';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

type Call = [method: string, ...args: unknown[]];

/** A stand-in query builder that records its calls and answers with `data`. */
function fakeClient(data: unknown) {
  const calls: Call[] = [];
  const builder: Record<string, unknown> = {
    then: (resolve: (value: unknown) => void) => {
      resolve({ data, error: null, status: 200 });
    },
  };
  for (const method of ['from', 'select', 'order', 'limit']) {
    builder[method] = (...args: unknown[]) => {
      calls.push([method, ...args]);
      return builder;
    };
  }
  vi.mocked(getSupabaseClient).mockReturnValue(
    builder as unknown as ReturnType<typeof getSupabaseClient>,
  );
  return calls;
}

const GOOD_ROW = {
  key: 'prospect',
  label: 'Prospect',
  group_label: 'Prospects',
  description: 'Companies that might buy from us.',
  colour: 'teal',
  sort_order: 10,
  archived_at: null,
};

describe('categoryListSchema', () => {
  it('accepts a well-formed row, and an archived one', () => {
    const archived = { ...GOOD_ROW, key: 'old_lead', archived_at: '2026-03-01T00:00:00.000Z' };
    expect(categoryListSchema.safeParse([GOOD_ROW, archived]).success).toBe(true);
  });

  it('accepts the seeded job-search preset', () => {
    expect(categoryListSchema.parse(sampleCategories)).toEqual(sampleCategories);
  });

  it('rejects a colour outside the palette', () => {
    expect(categoryListSchema.safeParse([{ ...GOOD_ROW, colour: 'red' }]).success).toBe(false);
  });

  it.each(['Prospect', '1st', 'has space', 'a'.repeat(32), ''])(
    'rejects the key %j',
    (key) => {
      expect(categoryListSchema.safeParse([{ ...GOOD_ROW, key }]).success).toBe(false);
    },
  );

  it('rejects an empty or over-long label', () => {
    expect(categoryListSchema.safeParse([{ ...GOOD_ROW, label: '' }]).success).toBe(false);
    const long = 'x'.repeat(41);
    expect(categoryListSchema.safeParse([{ ...GOOD_ROW, group_label: long }]).success).toBe(false);
  });
});

describe('statusLabelListSchema', () => {
  it('accepts a label for one of the six statuses', () => {
    const rows = [{ status: 'in_process', label: 'In a hiring process' }];
    expect(statusLabelListSchema.safeParse(rows).success).toBe(true);
  });

  it('rejects the old status name', () => {
    const rows = [{ status: 'in_hiring_process', label: 'In a hiring process' }];
    expect(statusLabelListSchema.safeParse(rows).success).toBe(false);
  });
});

describe('fetchCategories', () => {
  it('asks for every category, by sort order and then key', async () => {
    const calls = fakeClient(sampleCategories);
    await expect(fetchCategories()).resolves.toEqual(sampleCategories);
    expect(calls).toEqual([
      ['from', 'categories'],
      ['select', 'key,label,group_label,description,colour,sort_order,archived_at'],
      ['order', 'sort_order', { ascending: true }],
      ['order', 'key', { ascending: true }],
      ['limit', 100],
    ]);
  });

  it('refuses a list with a colour outside the palette', async () => {
    fakeClient([{ ...GOOD_ROW, colour: 'red' }]);
    await expect(fetchCategories()).rejects.toBeInstanceOf(UnexpectedDataError);
  });
});
