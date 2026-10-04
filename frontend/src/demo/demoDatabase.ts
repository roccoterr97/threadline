import { z } from 'zod';
import {
  categorySchema,
  personOverrideRowSchema,
  relevanceSchema,
  reviewAnswerSchema,
} from '../api/schemas';
import type { SupabaseResult } from '../api/client';
import { CategoryNameIndex } from '../domain/categorySettings';
import type { Clock } from '../lib/clock';
import type { Category } from '../types/database';
import { localDate } from './demoCalendar';
import type { DemoTables } from './demoData';
import { changeNotes, checkNoteChanges, checkNoteInsert, newNoteRow } from './demoNotes';
import { refreshIsRunning, settledRun, startedRefreshRun } from './demoRefresh';
import { conversationsWithPeople, peopleOverview } from './demoViews';

/**
 * The demo's in-memory database. It answers the same tables the real one
 * does, keeps its rules (a category in use cannot be deleted, keys are
 * unique, two categories never share a name or group name whatever the case,
 * a note is never blank and names a person who exists, text has length
 * limits) and forgets everything on reload.
 */

/** Chooses the rows a filter applies to. Rows are plain objects. */
export type RowFilter = (row: object) => boolean;

/** Postgres codes the real database answers with, so the dashboard reacts the same way. */
enum PostgresCode {
  ForeignKey = '23503',
  Unique = '23505',
  Check = '23514',
  UnknownTable = '42P01',
}

const OK_STATUS = 200;
const REFUSED_STATUS = 409;
const BAD_REQUEST_STATUS = 400;
const NOT_FOUND_STATUS = 404;
const REFRESH_STARTED_STATUS = 202;
const REFRESHING_STATUS = 409;

const categoryInsertSchema = categorySchema.omit({ archived_at: true });
const categoryChangesSchema = categorySchema.omit({ key: true }).partial();
const overrideWriteSchema = personOverrideRowSchema.omit({
  id: true,
  created_at: true,
  updated_at: true,
});
const personChangesSchema = z.object({ relevance: relevanceSchema });
const reviewAnswerChangesSchema = z.object({ answer: reviewAnswerSchema, answered_at: z.string() });

/** A successful answer carrying `data`. */
export function success(data: unknown = null): SupabaseResult {
  return { data, error: null, status: OK_STATUS };
}

function failure(code: PostgresCode, status = REFUSED_STATUS): SupabaseResult {
  return { data: null, error: { message: `demo refused: ${code}`, code }, status };
}

/** Postgres's name for the unique index on `categories.key`. */
const CATEGORY_KEY_INDEX = 'categories_key_key';

/** A duplicate refused by `index`, worded as Postgres words it so the index can be read back. */
function duplicate(index: string): SupabaseResult {
  const message = `duplicate key value violates unique constraint "${index}"`;
  return { data: null, error: { message, code: PostgresCode.Unique }, status: REFUSED_STATUS };
}

/** The answer to a query on a table the demo does not have. */
export const NO_SUCH_TABLE = failure(PostgresCode.UnknownTable, NOT_FOUND_STATUS);

/** A category name as the database compares it for clashes: case does not matter. */
function comparable(name: string): string {
  return name.trim().toLowerCase();
}

/** True when `name` is set and one of `others` already has it in `field`. */
function nameTaken(
  others: readonly Category[],
  field: 'label' | 'group_label',
  name: string | undefined,
): boolean {
  return name !== undefined && others.some((row) => comparable(row[field]) === comparable(name));
}

/**
 * The index a row `match` does not pick would break by taking the label or
 * group label in `changes`, or null when neither name is taken.
 */
function clashingIndex(
  categories: readonly Category[],
  match: RowFilter,
  changes: { label?: string | undefined; group_label?: string | undefined },
): CategoryNameIndex | null {
  const others = categories.filter((row) => !match(row));
  if (nameTaken(others, 'label', changes.label)) return CategoryNameIndex.Label;
  if (nameTaken(others, 'group_label', changes.group_label)) return CategoryNameIndex.GroupLabel;
  return null;
}

/** Applies `changes` to every row `match` picks, leaving the others as they are. */
function patch<T extends object>(rows: readonly T[], match: RowFilter, changes: Partial<T>): T[] {
  return rows.map((row) => (match(row) ? { ...row, ...changes } : row));
}

export class DemoDatabase {
  private sequence = 0;

  constructor(
    private readonly tables: DemoTables,
    private readonly clock: Clock,
  ) {}

  /** Every row of a table or view, before filters. */
  read(table: string): readonly object[] | null {
    const tables = this.tables;
    switch (table) {
      case 'people_overview':
        return peopleOverview(tables, localDate(this.clock.now()));
      case 'conversations':
        return conversationsWithPeople(tables);
      case 'categories':
        return tables.categories;
      case 'category_suggestions':
        return tables.suggestions;
      case 'status_labels':
        return tables.statusLabels;
      case 'person_overrides':
        return tables.overrides;
      case 'person_notes':
        return tables.notes;
      case 'review_items':
        return tables.reviewItems;
      case 'run_logs':
        return tables.runs.map((run) => settledRun(run, this.clock.now()));
      default:
        return null;
    }
  }

  /** Adds a row: a category from the settings page, or a note from a person's page. */
  insert(table: string, values: unknown): SupabaseResult {
    if (table === 'person_notes') return this.insertNote(values);
    if (table !== 'categories') return NO_SUCH_TABLE;
    const parsed = categoryInsertSchema.safeParse(values);
    if (!parsed.success) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
    const keyTaken = this.tables.categories.some((row) => row.key === parsed.data.key);
    if (keyTaken) return duplicate(CATEGORY_KEY_INDEX);
    const clash = clashingIndex(this.tables.categories, () => false, parsed.data);
    if (clash !== null) return duplicate(clash);
    this.tables.categories.push({ ...parsed.data, archived_at: null });
    return success();
  }

  /** Changes the rows `match` picks. */
  update(table: string, match: RowFilter, changes: unknown): SupabaseResult {
    const tables = this.tables;
    if (table === 'categories') {
      const parsed = categoryChangesSchema.safeParse(changes);
      if (!parsed.success) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
      const clash = clashingIndex(tables.categories, match, parsed.data);
      if (clash !== null) return duplicate(clash);
      tables.categories = patch(tables.categories, match, parsed.data);
      return success();
    }
    if (table === 'people') {
      const parsed = personChangesSchema.safeParse(changes);
      if (!parsed.success) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
      tables.people = patch(tables.people, match, parsed.data);
      return success();
    }
    if (table === 'review_items') {
      const parsed = reviewAnswerChangesSchema.safeParse(changes);
      if (!parsed.success) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
      tables.reviewItems = patch(tables.reviewItems, match, parsed.data);
      return success();
    }
    if (table === 'person_notes') {
      const checked = checkNoteChanges(changes);
      if ('reason' in checked) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
      const stamp = this.clock.now().toISOString();
      tables.notes = changeNotes(tables.notes, match, checked.body, stamp);
      return success();
    }
    return NO_SUCH_TABLE;
  }

  /** Adds a note, refusing one on nobody or one that breaks the text rules. */
  private insertNote(values: unknown): SupabaseResult {
    const people = new Set(this.tables.people.map((person) => person.id));
    const checked = checkNoteInsert(values, people);
    if ('reason' in checked) {
      return checked.reason === 'no_such_person'
        ? failure(PostgresCode.ForeignKey)
        : failure(PostgresCode.Check, BAD_REQUEST_STATUS);
    }
    const stamp = this.clock.now().toISOString();
    this.tables.notes.push(newNoteRow(this.nextId('note'), checked.note, stamp));
    return success();
  }

  /** Creates or replaces a person's correction. */
  upsert(table: string, values: unknown): SupabaseResult {
    if (table !== 'person_overrides') return NO_SUCH_TABLE;
    const parsed = overrideWriteSchema.safeParse(values);
    if (!parsed.success) return failure(PostgresCode.Check, BAD_REQUEST_STATUS);
    const stamp = this.clock.now().toISOString();
    const existing = this.tables.overrides.find((row) => row.person_id === parsed.data.person_id);
    const row = {
      id: existing?.id ?? this.nextId('override'),
      created_at: existing?.created_at ?? stamp,
      updated_at: stamp,
      ...parsed.data,
    };
    this.tables.overrides = [
      ...this.tables.overrides.filter((other) => other.person_id !== row.person_id),
      row,
    ];
    return success();
  }

  /** Deletes the rows `match` picks, refusing a category someone still has. */
  remove(table: string, match: RowFilter): SupabaseResult {
    const tables = this.tables;
    if (table === 'person_overrides') {
      tables.overrides = tables.overrides.filter((row) => !match(row));
      return success();
    }
    if (table === 'person_notes') {
      tables.notes = tables.notes.filter((row) => !match(row));
      return success();
    }
    if (table !== 'categories') return NO_SUCH_TABLE;
    const doomed = new Set(tables.categories.filter(match).map((row) => row.key));
    const inUse =
      tables.people.some((row) => doomed.has(row.person_type)) ||
      tables.overrides.some((row) => row.person_type !== null && doomed.has(row.person_type));
    if (inUse) return failure(PostgresCode.ForeignKey);
    tables.categories = tables.categories.filter((row) => !doomed.has(row.key));
    return success();
  }

  /**
   * Starts the pretend "Refresh now" run and answers as the refresh service
   * would: with the moment it was asked for, or "already running".
   */
  startRefresh(): { status: number; body: object } {
    const now = this.clock.now();
    if (refreshIsRunning(this.tables.runs, now)) {
      return { status: REFRESHING_STATUS, body: { code: 'already_running' } };
    }
    this.sequence += 1;
    this.tables.runs = [startedRefreshRun(this.sequence, now), ...this.tables.runs];
    return {
      status: REFRESH_STARTED_STATUS,
      body: { code: 'started', requested_at: now.toISOString() },
    };
  }

  private nextId(prefix: string): string {
    this.sequence += 1;
    return `demo-${prefix}-${this.sequence}`;
  }
}
