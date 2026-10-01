import type { Category, CategoryKey, PeopleOverviewRow } from '../types/database';
import { categoriesInUse } from './categories';
import {
  ACTIVE,
  CONTACT_STATUSES,
  DEFAULT_FILTERS,
  isActiveStatus,
  NOT_ASSESSED,
  statusKeyOf,
  type PeopleFilters,
  type StatusKey,
} from './peopleView';

/** The five numbers at the top of the home page. */
export interface PeopleCounters {
  actionsForMe: number;
  overdue: number;
  timeToChase: number;
  waitingOnThem: number;
  activeConversations: number;
}

/** One of the five headline numbers. */
export type CounterKey = keyof PeopleCounters;

/** The five counters, in the order the home page shows them. */
export const COUNTER_KEYS = [
  'actionsForMe',
  'overdue',
  'timeToChase',
  'waitingOnThem',
  'activeConversations',
] as const satisfies readonly CounterKey[];

/** The one filter each counter stands for; every other filter stays cleared. */
const COUNTER_FILTERS: Record<CounterKey, Partial<PeopleFilters>> = {
  actionsForMe: { waiting: 'me' },
  overdue: { due: 'overdue' },
  timeToChase: { due: 'chase' },
  waitingOnThem: { waiting: 'them' },
  activeConversations: { status: ACTIVE },
};

/** The filters that show exactly the people a counter counts. */
export function counterFilters(key: CounterKey): PeopleFilters {
  return { ...DEFAULT_FILTERS, ...COUNTER_FILTERS[key] };
}

/** True when the list is showing exactly the people behind this counter. */
export function isCounterShown(key: CounterKey, filters: PeopleFilters): boolean {
  const expected = counterFilters(key);
  return (
    filters.type === expected.type &&
    filters.status === expected.status &&
    filters.waiting === expected.waiting &&
    filters.due === expected.due
  );
}

const NO_COUNTERS: PeopleCounters = {
  actionsForMe: 0,
  overdue: 0,
  timeToChase: 0,
  waitingOnThem: 0,
  activeConversations: 0,
};

function one(condition: boolean): number {
  return condition ? 1 : 0;
}

/**
 * Counts the headline numbers from the same rows the table shows, so the
 * counters and the table can never disagree.
 *
 * The counters always describe the whole list, never the filtered view.
 * "Overdue" and "time to chase" come from two flags the database keeps apart
 * (waiting on me versus waiting on them), so no row is ever in both.
 */
export function countPeople(people: readonly PeopleOverviewRow[]): PeopleCounters {
  return people.reduce<PeopleCounters>(
    (totals, row) => ({
      actionsForMe: totals.actionsForMe + one(row.waiting_on === 'me'),
      overdue: totals.overdue + one(row.is_overdue),
      timeToChase: totals.timeToChase + one(row.is_chase_due),
      waitingOnThem: totals.waitingOnThem + one(row.waiting_on === 'them'),
      activeConversations: totals.activeConversations + one(isActiveStatus(row.status)),
    }),
    NO_COUNTERS,
  );
}

/** A count for each category key. */
export type CountsByType = Record<CategoryKey, number>;

/** One line of the status grid: a status, its count per type, and its total. */
export interface StatusGridRow {
  status: StatusKey;
  counts: CountsByType;
  total: number;
}

/** How many people of each type sit in each status, with the totals. */
export interface StatusGrid {
  /** The categories across the top, in the order they are shown. */
  columns: Category[];
  rows: StatusGridRow[];
  columnTotals: CountsByType;
  total: number;
}

function emptyCountsByType(columns: readonly Category[]): CountsByType {
  return Object.fromEntries(columns.map((column) => [column.key, 0]));
}

function sumCounts(counts: CountsByType): number {
  return Object.values(counts).reduce((sum, count) => sum + count, 0);
}

function addOne(counts: CountsByType, key: CategoryKey): void {
  counts[key] = (counts[key] ?? 0) + 1;
}

/**
 * Counts people by status (rows) and category (columns) for the home-page grid.
 *
 * Every status gets a row, even at zero, so the grid always has the same
 * shape. The "not looked at yet" row only appears when someone has no status.
 * The columns are `categoriesInUse`, which always covers every person's
 * category. Pure: every person lands in exactly one cell, so the totals add up.
 */
export function countByTypeAndStatus(
  people: readonly PeopleOverviewRow[],
  categories: readonly Category[],
): StatusGrid {
  const columns = categoriesInUse(categories, people);
  const cells = new Map<StatusKey, CountsByType>();
  const columnTotals = emptyCountsByType(columns);

  for (const row of people) {
    const key = statusKeyOf(row);
    const counts = cells.get(key) ?? emptyCountsByType(columns);
    addOne(counts, row.person_type);
    cells.set(key, counts);
    addOne(columnTotals, row.person_type);
  }

  const statuses: StatusKey[] = cells.has(NOT_ASSESSED)
    ? [...CONTACT_STATUSES, NOT_ASSESSED]
    : [...CONTACT_STATUSES];

  const rows = statuses.map((status) => {
    const counts = cells.get(status) ?? emptyCountsByType(columns);
    return { status, counts, total: sumCounts(counts) };
  });

  return { columns, rows, columnTotals, total: sumCounts(columnTotals) };
}
