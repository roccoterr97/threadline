import type { SupabaseResult } from '../api/client';
import { NO_SUCH_TABLE, success, type DemoDatabase, type RowFilter } from './demoDatabase';

/**
 * The slice of the Supabase query builder the dashboard's data layer uses,
 * answered from the demo database. Each call records what was asked; the
 * query runs when it is awaited, exactly like the real one.
 */

type Action =
  | { kind: 'select' }
  | { kind: 'insert'; values: unknown }
  | { kind: 'update'; changes: unknown }
  | { kind: 'upsert'; values: unknown }
  | { kind: 'delete' };

interface OrderOptions {
  ascending?: boolean;
  nullsFirst?: boolean;
  referencedTable?: string;
}

interface LimitOptions {
  referencedTable?: string;
}

interface Ordering {
  column: string;
  ascending: boolean;
  nullsFirst: boolean;
}

function valueOf(row: object, column: string): unknown {
  return Object.getOwnPropertyDescriptor(row, column)?.value as unknown;
}

function compareValues(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

function byOrderings(orderings: readonly Ordering[]) {
  return (left: object, right: object): number => {
    for (const { column, ascending, nullsFirst } of orderings) {
      const a = valueOf(left, column);
      const b = valueOf(right, column);
      if (a === b) continue;
      if (a === null) return nullsFirst ? -1 : 1;
      if (b === null) return nullsFirst ? 1 : -1;
      const order = compareValues(a, b);
      if (order !== 0) return ascending ? order : -order;
    }
    return 0;
  };
}

/** Postgres comparisons: anything compared with null is false. */
function compared(column: string, value: string, test: (order: number) => boolean): RowFilter {
  return (row) => {
    const cell = valueOf(row, column);
    return cell !== null && cell !== undefined && test(compareValues(cell, value));
  };
}

export class DemoQuery implements PromiseLike<SupabaseResult> {
  private action: Action = { kind: 'select' };
  private readonly filters: RowFilter[] = [];
  private readonly orderings: Ordering[] = [];
  private readonly embeddedOrderings = new Map<string, Ordering[]>();
  private readonly embeddedLimits = new Map<string, number>();
  private rowLimit: number | null = null;
  private firstRow = 0;
  private single = false;

  constructor(
    private readonly database: DemoDatabase,
    private readonly table: string,
  ) {}

  select(_columns?: string): this {
    return this;
  }

  insert(values: unknown): this {
    this.action = { kind: 'insert', values };
    return this;
  }

  update(changes: unknown): this {
    this.action = { kind: 'update', changes };
    return this;
  }

  upsert(values: unknown, _options?: { onConflict?: string }): this {
    this.action = { kind: 'upsert', values };
    return this;
  }

  delete(): this {
    this.action = { kind: 'delete' };
    return this;
  }

  eq(column: string, value: unknown): this {
    this.filters.push((row) => valueOf(row, column) === value);
    return this;
  }

  neq(column: string, value: unknown): this {
    this.filters.push((row) => valueOf(row, column) !== value);
    return this;
  }

  is(column: string, value: null): this {
    this.filters.push((row) => valueOf(row, column) === value);
    return this;
  }

  gte(column: string, value: string): this {
    this.filters.push(compared(column, value, (order) => order >= 0));
    return this;
  }

  lt(column: string, value: string): this {
    this.filters.push(compared(column, value, (order) => order < 0));
    return this;
  }

  /** Orders the rows, or the rows embedded under `referencedTable`. */
  order(column: string, options: OrderOptions = {}): this {
    const ascending = options.ascending ?? true;
    const ordering = { column, ascending, nullsFirst: options.nullsFirst ?? !ascending };
    const table = options.referencedTable;
    if (table === undefined) this.orderings.push(ordering);
    else this.embeddedOrderings.set(table, [...(this.embeddedOrderings.get(table) ?? []), ordering]);
    return this;
  }

  /** Caps the rows, or the rows embedded under `referencedTable` in each row. */
  limit(count: number, options: LimitOptions = {}): this {
    if (options.referencedTable === undefined) this.rowLimit = count;
    else this.embeddedLimits.set(options.referencedTable, count);
    return this;
  }

  /** Takes rows `from` to `to`, both counted from 0 and both included, like the real one. */
  range(from: number, to: number): this {
    this.firstRow = from;
    this.rowLimit = to - from + 1;
    return this;
  }

  maybeSingle(): this {
    this.single = true;
    return this;
  }

  then<TResult1 = SupabaseResult, TResult2 = never>(
    onfulfilled?: ((value: SupabaseResult) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return Promise.resolve().then(() => this.run()).then(onfulfilled, onrejected);
  }

  private matches(row: object): boolean {
    return this.filters.every((filter) => filter(row));
  }

  /** Orders and caps each list embedded in a row, as asked with `referencedTable`. */
  private shapeEmbedded(row: object): object {
    const shaped: Record<string, object[]> = {};
    const tables = new Set([...this.embeddedOrderings.keys(), ...this.embeddedLimits.keys()]);
    for (const table of tables) {
      const embedded: unknown = valueOf(row, table);
      if (!Array.isArray(embedded)) continue;
      const items = embedded.filter((item): item is object => typeof item === 'object' && item !== null);
      const ordered = items.sort(byOrderings(this.embeddedOrderings.get(table) ?? []));
      shaped[table] = ordered.slice(0, this.embeddedLimits.get(table));
    }
    return { ...row, ...shaped };
  }

  private run(): SupabaseResult {
    const match = (row: object) => this.matches(row);
    switch (this.action.kind) {
      case 'insert':
        return this.database.insert(this.table, this.action.values);
      case 'update':
        return this.database.update(this.table, match, this.action.changes);
      case 'upsert':
        return this.database.upsert(this.table, this.action.values);
      case 'delete':
        return this.database.remove(this.table, match);
      case 'select':
        return this.runSelect();
    }
  }

  private runSelect(): SupabaseResult {
    const rows = this.database.read(this.table);
    if (rows === null) return NO_SUCH_TABLE;
    const found = rows.filter((row) => this.matches(row)).sort(byOrderings(this.orderings));
    const end = this.rowLimit === null ? undefined : this.firstRow + this.rowLimit;
    const limited = found.slice(this.firstRow, end);
    // A copy, so the page can never change the demo's tables by accident.
    const copies = structuredClone(limited).map((row) => this.shapeEmbedded(row));
    return success(this.single ? (copies[0] ?? null) : copies);
  }
}
