import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NOW } from '../test/__fixtures__/sampleData';
import { RefusalReason, RefusedError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import {
  addCategory,
  removeCategory,
  RemovalOutcome,
  saveCategoryOrder,
  showCategoryAgain,
} from './categoryEdits';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

type Call = [method: string, ...args: unknown[]];

interface Answer {
  error: { message: string; code: string } | null;
  status: number;
}

const OK: Answer = { error: null, status: 204 };

/**
 * A stand-in query builder. It records every call, and each awaited query
 * takes the next answer from `answers` (then keeps answering "ok").
 */
function fakeClient(answers: Answer[]): Call[] {
  const calls: Call[] = [];
  const queue = [...answers];
  const builder: Record<string, unknown> = {
    then: (resolve: (value: unknown) => void) => {
      resolve({ data: null, ...(queue.shift() ?? OK) });
    },
  };
  for (const method of ['from', 'insert', 'update', 'delete', 'eq']) {
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

function refusal(code: string): Answer {
  return { error: { message: 'raw database words', code }, status: 409 };
}

let calls: Call[];

beforeEach(() => {
  calls = fakeClient([]);
});

describe('removeCategory', () => {
  it('deletes a category nobody has', async () => {
    await expect(removeCategory('mentor', NOW)).resolves.toBe(RemovalOutcome.Deleted);
    expect(calls).toEqual([
      ['from', 'categories'],
      ['delete'],
      ['eq', 'key', 'mentor'],
    ]);
  });

  it('hides a category instead when people still have it (23503)', async () => {
    calls = fakeClient([refusal('23503')]);
    await expect(removeCategory('network', NOW)).resolves.toBe(RemovalOutcome.Archived);
    expect(calls.slice(3)).toEqual([
      ['from', 'categories'],
      ['update', { archived_at: NOW.toISOString() }],
      ['eq', 'key', 'network'],
    ]);
  });

  it('passes on a refusal for any other reason, without hiding anything', async () => {
    calls = fakeClient([refusal('23514')]);
    const removal = removeCategory('unknown', NOW);
    await expect(removal).rejects.toBeInstanceOf(RefusedError);
    await expect(removal).rejects.toMatchObject({ reason: RefusalReason.BreaksRule });
    expect(calls.some(([method]) => method === 'update')).toBe(false);
  });
});

describe('the other edits', () => {
  it('adds a category with every column the owner chose', async () => {
    const category = {
      key: 'mentor',
      label: 'Mentor',
      group_label: 'Mentors',
      description: 'People who advise me.',
      colour: 'teal' as const,
      sort_order: 40,
    };
    await addCategory(category);
    expect(calls).toEqual([
      ['from', 'categories'],
      ['insert', category],
    ]);
  });

  it('refuses a ninth category in use with a plain reason (23514)', async () => {
    calls = fakeClient([refusal('23514')]);
    await expect(showCategoryAgain('network')).rejects.toMatchObject({
      reason: RefusalReason.BreaksRule,
    });
  });

  it('saves each new position as its own update', async () => {
    await saveCategoryOrder([
      { key: 'vc', sort_order: 10 },
      { key: 'startup', sort_order: 20 },
    ]);
    expect(calls.filter(([method]) => method === 'update')).toEqual([
      ['update', { sort_order: 10 }],
      ['update', { sort_order: 20 }],
    ]);
  });
});
