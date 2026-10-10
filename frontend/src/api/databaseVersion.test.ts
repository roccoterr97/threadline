// @vitest-environment node
import { readdirSync, readFileSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataUnavailableError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import { isDatabaseOlder, NEWEST_NEEDED } from './databaseVersion';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

const limit = vi.fn();
const select = vi.fn(() => ({ limit }));
const from = vi.fn(() => ({ select }));

beforeEach(() => {
  vi.mocked(getSupabaseClient).mockReturnValue({ from } as unknown as ReturnType<
    typeof getSupabaseClient
  >);
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('isDatabaseOlder', () => {
  it('asks for no rows of the newest table the dashboard needs', async () => {
    limit.mockResolvedValue({ data: [], error: null });

    await expect(isDatabaseOlder()).resolves.toBe(false);
    expect(from).toHaveBeenCalledWith(NEWEST_NEEDED.table);
    expect(select).toHaveBeenCalledWith(NEWEST_NEEDED.columns);
    expect(limit).toHaveBeenCalledWith(0);
  });

  it.each([
    ['a missing table', { code: 'PGRST205', message: 'not found' }, 404],
    ['a missing table (Postgres)', { code: '42P01', message: 'no relation' }, 404],
    ['a missing column', { code: '42703', message: 'no column' }, 400],
  ])('is true for %s', async (_label, error, status) => {
    limit.mockResolvedValue({ data: null, error, status });

    await expect(isDatabaseOlder()).resolves.toBe(true);
  });

  it('cannot say when the database does not answer', async () => {
    limit.mockResolvedValue({ data: null, error: { message: 'down', code: '57P01' }, status: 503 });

    await expect(isDatabaseOlder()).rejects.toBeInstanceOf(DataUnavailableError);
  });
});

describe('NEWEST_NEEDED', () => {
  const backend = readFileSync(
    new URL('../../../backend/src/tracker/services/database_structure.py', import.meta.url),
    'utf8',
  );
  const migrations = readdirSync(new URL('../../../supabase/migrations/', import.meta.url));

  it('names a structure file that exists', () => {
    expect(migrations).toContain(`${NEWEST_NEEDED.migration}.sql`);
  });

  it('asks for the same mark the set-up checks for that file', () => {
    expect(backend).toContain(
      `"${NEWEST_NEEDED.migration}": ColumnsProbe("${NEWEST_NEEDED.table}", "${NEWEST_NEEDED.columns}")`,
    );
  });
});
