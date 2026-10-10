import { z } from 'zod';
import { TableMissingError } from '../lib/errors';
import { getSupabaseClient } from '../lib/supabaseClient';
import { runQuery } from './client';

/**
 * Whether the owner's database has everything this dashboard reads.
 *
 * The shared dashboard always runs the newest code, while an owner's database
 * only changes when they apply the newest structure files. The database keeps
 * no version number, so this asks for the one thing the newest file the
 * dashboard depends on created, the same mark the set-up checks for that file
 * (`KNOWN_MIGRATIONS` in `backend/src/tracker/services/database_structure.py`).
 *
 * MOVED BY HAND: when a new file under `supabase/migrations/` adds a table or
 * a column the dashboard reads, point `NEWEST_NEEDED` at that file and its
 * mark. A test checks that the mark below matches the set-up's one for the
 * same file; nothing can check that it was moved forward.
 */
export const NEWEST_NEEDED = {
  migration: '0016_person_notes',
  table: 'person_notes',
  columns: 'id,person_id',
} as const;

export const databaseVersionQueryKey = ['database-version'] as const;

const anyRows = z.array(z.unknown());

/**
 * Asks for no rows of the newest table the dashboard needs, which costs one
 * small request and reads nothing.
 *
 * @returns True when the database lacks it, so it is older than this dashboard.
 * @throws {DataUnavailableError} when the question could not be answered.
 */
export async function isDatabaseOlder(): Promise<boolean> {
  const supabase = getSupabaseClient();
  try {
    await runQuery('database.version', anyRows, () =>
      supabase.from(NEWEST_NEEDED.table).select(NEWEST_NEEDED.columns).limit(0),
    );
    return false;
  } catch (error: unknown) {
    if (error instanceof TableMissingError) return true;
    throw error;
  }
}
