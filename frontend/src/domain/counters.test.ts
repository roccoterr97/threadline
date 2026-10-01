import { describe, expect, it } from 'vitest';
import {
  peopleWithCategories,
  salesCategories,
  sampleCategories,
  samplePeople,
  singleCategory,
  withArchived,
} from '../test/__fixtures__/sampleData';
import type { PeopleOverviewRow } from '../types/database';
import {
  COUNTER_KEYS,
  counterFilters,
  countByTypeAndStatus,
  countPeople,
  isCounterShown,
} from './counters';
import { applyPeopleView, DEFAULT_FILTERS, DEFAULT_VIEW } from './peopleView';

const ZERO = {
  actionsForMe: 0,
  overdue: 0,
  timeToChase: 0,
  waitingOnThem: 0,
  activeConversations: 0,
};

function notAssessed(id: string): PeopleOverviewRow {
  return {
    ...samplePeople[0]!,
    person_id: id,
    status: null,
    waiting_on: null,
    is_overdue: false,
    is_chase_due: false,
  };
}

describe('countPeople', () => {
  it('matches a hand count of the sample data', () => {
    // Counted by hand from src/test/__fixtures__/sampleData.ts:
    //   waiting on me:   Ana, Dan, Elin, Ines               -> 4
    //   overdue:         Dan, Elin (waiting on me, late)    -> 2
    //   time to chase:   Kira (waiting on them, late)       -> 1
    //   waiting on them: Ben, Carla, Greta, Hugo, Kira      -> 5
    //   active:          Ana, Carla, Dan, Greta, Ines, Jonas-> 6
    expect(countPeople(samplePeople)).toEqual({
      actionsForMe: 4,
      overdue: 2,
      timeToChase: 1,
      waitingOnThem: 5,
      activeConversations: 6,
    });
  });

  it('returns zeroes for an empty list', () => {
    expect(countPeople([])).toEqual(ZERO);
  });

  it('does not count a person the assistant has not looked at yet', () => {
    expect(countPeople([notAssessed('p-99')])).toEqual(ZERO);
  });

  it('counts only the three statuses that mean a live conversation', () => {
    const closed = { ...samplePeople[0]!, status: 'closed' as const };
    const quiet = { ...samplePeople[1]!, status: 'gone_quiet' as const };
    const noReply = { ...samplePeople[2]!, status: 'contacted_no_reply' as const };
    expect(countPeople([closed, quiet, noReply]).activeConversations).toBe(0);
  });

  it('never counts the same person as both overdue and time to chase', () => {
    const counted = countPeople(samplePeople);
    const flagged = samplePeople.filter((row) => row.is_overdue || row.is_chase_due).length;
    expect(counted.overdue + counted.timeToChase).toBe(flagged);
    expect(samplePeople.some((row) => row.is_overdue && row.is_chase_due)).toBe(false);
  });
});

describe('countByTypeAndStatus', () => {
  it('puts each person in the cell for their status and type', () => {
    const grid = countByTypeAndStatus(samplePeople, sampleCategories);
    const inProcess = grid.rows.find((row) => row.status === 'in_process');
    expect(inProcess?.counts).toEqual({ startup: 0, vc: 1, network: 1, unknown: 0 });
    expect(grid.columnTotals).toEqual({ startup: 5, vc: 3, network: 3, unknown: 1 });
  });

  it('adds up across rows, across columns and to the number of people', () => {
    const people = [...samplePeople, notAssessed('p-98'), notAssessed('p-99')];
    const grid = countByTypeAndStatus(people, sampleCategories);
    const keys = grid.columns.map((column) => column.key);

    for (const row of grid.rows) {
      const rowSum = keys.reduce((sum, key) => sum + (row.counts[key] ?? 0), 0);
      expect(row.total).toBe(rowSum);
    }
    for (const key of keys) {
      const columnSum = grid.rows.reduce((sum, row) => sum + (row.counts[key] ?? 0), 0);
      expect(grid.columnTotals[key]).toBe(columnSum);
    }
    const rowTotals = grid.rows.reduce((sum, row) => sum + row.total, 0);
    expect(rowTotals).toBe(people.length);
    expect(grid.total).toBe(people.length);
  });

  it('shows every status even when nobody has it', () => {
    const grid = countByTypeAndStatus([], sampleCategories);
    expect(grid.rows.map((row) => row.status)).toEqual([
      'contacted_no_reply',
      'in_conversation',
      'meeting_planned',
      'in_process',
      'gone_quiet',
      'closed',
    ]);
    expect(grid.total).toBe(0);
  });

  it('adds a "not looked at yet" row only when someone has no status', () => {
    const rows = countByTypeAndStatus(samplePeople, sampleCategories).rows;
    expect(rows.some((row) => row.status === 'none')).toBe(false);
    const grid = countByTypeAndStatus([...samplePeople, notAssessed('p-99')], sampleCategories);
    expect(grid.rows.at(-1)).toEqual({
      status: 'none',
      counts: { startup: 1, vc: 0, network: 0, unknown: 0 },
      total: 1,
    });
  });
});

describe('countByTypeAndStatus — other profiles', () => {
  it('gives a five-category profile one column per category, in order', () => {
    const people = peopleWithCategories(['prospect', 'customer', 'partner', 'referrer']);
    const grid = countByTypeAndStatus(people, salesCategories);

    expect(grid.columns.map((column) => column.key)).toEqual([
      'prospect',
      'customer',
      'partner',
      'referrer',
      'unknown',
    ]);
    expect(grid.columnTotals).toEqual({
      prospect: 3,
      customer: 3,
      partner: 3,
      referrer: 3,
      unknown: 0,
    });
    expect(grid.total).toBe(12);
  });

  it('works with a single category of its own', () => {
    const grid = countByTypeAndStatus(peopleWithCategories(['member']), singleCategory);
    expect(grid.columns.map((column) => column.key)).toEqual(['member', 'unknown']);
    expect(grid.columnTotals).toEqual({ member: 12, unknown: 0 });
  });

  it('keeps an archived category as a column only while someone has it', () => {
    const archived = withArchived(sampleCategories, 'network');
    const withNetwork = countByTypeAndStatus(samplePeople, archived);
    expect(withNetwork.columns.map((column) => column.key)).toContain('network');
    expect(withNetwork.columnTotals.network).toBe(3);

    const withoutNetwork = samplePeople.filter((person) => person.person_type !== 'network');
    const grid = countByTypeAndStatus(withoutNetwork, archived);
    expect(grid.columns.map((column) => column.key)).toEqual(['startup', 'vc', 'unknown']);
  });

  it('still counts a person whose category the list does not know', () => {
    const stray = { ...samplePeople[0]!, person_id: 'p-97', person_type: 'mystery' };
    const grid = countByTypeAndStatus([...samplePeople, stray], sampleCategories);
    expect(grid.columns.at(-1)).toMatchObject({ key: 'mystery', label: 'mystery', colour: 'grey' });
    expect(grid.columnTotals.mystery).toBe(1);
    expect(grid.total).toBe(13);
  });
});

describe('counterFilters', () => {
  it.each([
    ['actionsForMe', { waiting: 'me' }],
    ['overdue', { due: 'overdue' }],
    ['timeToChase', { due: 'chase' }],
    ['waitingOnThem', { waiting: 'them' }],
    ['activeConversations', { status: 'active' }],
  ] as const)('opens %s with only its own filter', (key, expected) => {
    expect(counterFilters(key)).toEqual({ ...DEFAULT_FILTERS, ...expected });
  });

  it('shows exactly as many people as each counter says', () => {
    const counted = countPeople(samplePeople);
    for (const key of COUNTER_KEYS) {
      const shown = applyPeopleView(samplePeople, { ...DEFAULT_VIEW, ...counterFilters(key) });
      expect(shown).toHaveLength(counted[key]);
    }
  });
});

describe('isCounterShown', () => {
  it('is true when the filters are exactly the counter\'s own', () => {
    expect(isCounterShown('overdue', counterFilters('overdue'))).toBe(true);
  });

  it('is false when another filter is also on', () => {
    expect(isCounterShown('overdue', { ...counterFilters('overdue'), type: 'vc' })).toBe(false);
  });

  it('is false with no filter on', () => {
    expect(COUNTER_KEYS.some((key) => isCounterShown(key, DEFAULT_FILTERS))).toBe(false);
  });
});
