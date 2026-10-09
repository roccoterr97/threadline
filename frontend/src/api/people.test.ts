import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PEOPLE_MAX_ROWS, PEOPLE_PAGE_SIZE } from '../constants/dashboard';
import { DataUnavailableError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import { samplePerson } from '../test/__fixtures__/sampleData';
import type { PeopleOverviewRow } from '../types/database';
import { fetchPeople } from './people';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

/** What the fake database answers for one page. */
type PageAnswer = { data: unknown; error: { message: string } | null };

/**
 * A stand-in for the Supabase query builder over `rows`: it honours `.range()`
 * the way PostgREST does and records each request it was given.
 */
function fakeClient(rows: readonly unknown[], failOnRequest?: number) {
  const requests: Array<{ from: number; to: number }> = [];
  const client = {
    from: () => {
      const request = { from: 0, to: rows.length - 1 };
      const builder: Record<string, unknown> = {};
      builder.select = () => builder;
      builder.order = () => builder;
      builder.limit = (count: number) => {
        request.to = count - 1;
        return builder;
      };
      builder.range = (from: number, to: number) => {
        request.from = from;
        request.to = to;
        return builder;
      };
      builder.then = (resolve: (answer: PageAnswer & { status: number }) => void) => {
        requests.push({ ...request });
        const failed = failOnRequest === requests.length;
        resolve({
          data: failed ? null : rows.slice(request.from, request.to + 1),
          error: failed ? { message: 'down' } : null,
          status: failed ? 500 : 200,
        });
      };
      return builder;
    },
  };
  return { client, requests };
}

function manyPeople(count: number): PeopleOverviewRow[] {
  const template = samplePerson();
  return Array.from({ length: count }, (_, index) => ({
    ...template,
    person_id: `person-${String(index).padStart(5, '0')}`,
  }));
}

function useDatabase(fake: ReturnType<typeof fakeClient>) {
  vi.mocked(getSupabaseClient).mockReturnValue(
    fake.client as unknown as ReturnType<typeof getSupabaseClient>,
  );
}

beforeEach(() => {
  vi.mocked(getSupabaseClient).mockReset();
});

describe('fetchPeople', () => {
  it('reads a short list in one request', async () => {
    const fake = fakeClient(manyPeople(3));
    useDatabase(fake);
    await expect(fetchPeople()).resolves.toHaveLength(3);
    expect(fake.requests).toHaveLength(1);
  });

  it('keeps reading until it has everyone, not just the first page', async () => {
    const total = PEOPLE_PAGE_SIZE * 2 + 120;
    const fake = fakeClient(manyPeople(total));
    useDatabase(fake);
    const people = await fetchPeople();
    expect(people).toHaveLength(total);
    expect(people.map((person) => person.person_id)).toEqual(
      manyPeople(total).map((person) => person.person_id),
    );
    expect(fake.requests).toHaveLength(3);
  });

  it('asks for one more page when the list ends exactly on a page boundary', async () => {
    const fake = fakeClient(manyPeople(PEOPLE_PAGE_SIZE));
    useDatabase(fake);
    await expect(fetchPeople()).resolves.toHaveLength(PEOPLE_PAGE_SIZE);
    expect(fake.requests).toHaveLength(2);
  });

  it('lists a person once even when a page overlaps the one before', async () => {
    const rows = manyPeople(PEOPLE_PAGE_SIZE + 5);
    // Someone new arrived mid-read, so row 499 shows up again as row 500.
    const shifted = [...rows.slice(0, PEOPLE_PAGE_SIZE), rows[PEOPLE_PAGE_SIZE - 1], ...rows.slice(PEOPLE_PAGE_SIZE)];
    useDatabase(fakeClient(shifted));
    const people = await fetchPeople();
    expect(new Set(people.map((person) => person.person_id)).size).toBe(people.length);
    expect(people).toHaveLength(rows.length);
  });

  it('stops at the safety cap instead of reading without end', async () => {
    const fake = fakeClient(manyPeople(PEOPLE_MAX_ROWS + PEOPLE_PAGE_SIZE));
    useDatabase(fake);
    const people = await fetchPeople();
    expect(people).toHaveLength(PEOPLE_MAX_ROWS);
    expect(fake.requests).toHaveLength(PEOPLE_MAX_ROWS / PEOPLE_PAGE_SIZE);
  });

  it('fails as a whole when a later page cannot be read', async () => {
    useDatabase(fakeClient(manyPeople(PEOPLE_PAGE_SIZE * 2), 2));
    await expect(fetchPeople()).rejects.toBeInstanceOf(DataUnavailableError);
  });
});
