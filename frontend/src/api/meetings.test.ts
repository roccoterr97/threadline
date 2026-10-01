import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getSupabaseClient } from '../lib/supabaseClient';
import { NOW, sampleMeetings } from '../test/__fixtures__/sampleData';
import { fetchUpcomingMeetings } from './meetings';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

type Call = [method: string, ...args: unknown[]];

/**
 * A stand-in for the Supabase query builder: it records every call made on it
 * and answers with `data` once awaited.
 */
function fakeClient(data: unknown) {
  const calls: Call[] = [];
  const builder: Record<string, unknown> = {
    then: (resolve: (value: unknown) => void) => {
      resolve({ data, error: null, status: 200 });
    },
  };
  for (const method of ['from', 'select', 'eq', 'neq', 'gte', 'lt', 'order', 'limit']) {
    builder[method] = (...args: unknown[]) => {
      calls.push([method, ...args]);
      return builder;
    };
  }
  return { client: builder, calls };
}

let calls: Call[];

beforeEach(() => {
  const fake = fakeClient(sampleMeetings);
  calls = fake.calls;
  vi.mocked(getSupabaseClient).mockReturnValue(
    fake.client as unknown as ReturnType<typeof getSupabaseClient>,
  );
});

describe('fetchUpcomingMeetings', () => {
  it('returns the meetings once they match the expected shape', async () => {
    await expect(fetchUpcomingMeetings(NOW)).resolves.toEqual(sampleMeetings);
  });

  it('asks only for calendar meetings in the next seven days, soonest first', async () => {
    await fetchUpcomingMeetings(NOW);
    expect(calls).toEqual([
      ['from', 'conversations'],
      ['select', 'id, subject, meeting_at, person_id, people(full_name, organisations(name))'],
      ['eq', 'channel', 'calendar'],
      ['neq', 'relevance', 'noise'],
      ['gte', 'meeting_at', '2026-03-12T09:00:00.000Z'],
      ['lt', 'meeting_at', '2026-03-19T09:00:00.000Z'],
      ['order', 'meeting_at', { ascending: true }],
      ['limit', 20],
    ]);
  });
});
