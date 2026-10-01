import { describe, expect, it } from 'vitest';
import {
  peopleWithCategories,
  salesCategories,
  sampleCategories,
  samplePeople,
  singleCategory,
} from '../test/__fixtures__/sampleData';
import type { PeopleOverviewRow } from '../types/database';
import { categoriesInUse } from './categories';
import {
  applyPeopleView,
  clearFilters,
  DEFAULT_VIEW,
  readPeopleView,
  writePeopleView,
  type PeopleView,
} from './peopleView';

function view(overrides: Partial<PeopleView>): PeopleView {
  return { ...DEFAULT_VIEW, sort: 'name', ...overrides };
}

/** The type keys the job-search preset offers. */
const TYPE_KEYS = sampleCategories.map((category) => category.key);

function names(rows: readonly PeopleOverviewRow[]): string[] {
  return rows.map((row) => row.full_name);
}

describe('readPeopleView', () => {
  it('reads every filter and the sort out of the address', () => {
    const params = new URLSearchParams(
      'type=vc&status=in_conversation&waiting=me&due=chase&sort=due-date',
    );
    expect(readPeopleView(params, TYPE_KEYS)).toEqual({
      type: 'vc',
      status: 'in_conversation',
      waiting: 'me',
      due: 'chase',
      sort: 'due-date',
    });
  });

  it('falls back to the defaults when the address is empty', () => {
    expect(readPeopleView(new URLSearchParams(), TYPE_KEYS)).toEqual(DEFAULT_VIEW);
  });

  it('ignores values that are not real options', () => {
    const params = new URLSearchParams(
      'type=robot&status=happy&waiting=everyone&due=soon&sort=whatever&show=nonsense',
    );
    expect(readPeopleView(params, TYPE_KEYS)).toEqual(DEFAULT_VIEW);
  });

  it('reads the "not looked at yet" status', () => {
    expect(readPeopleView(new URLSearchParams('status=none'), TYPE_KEYS).status).toBe('none');
  });

  it('reads the "active" status group', () => {
    expect(readPeopleView(new URLSearchParams('status=active'), TYPE_KEYS).status).toBe('active');
  });
});

describe('readPeopleView — categories from the database', () => {
  it('reads a type only when it is one of the keys it was given', () => {
    const params = new URLSearchParams('type=customer');
    const keys = categoriesInUse(salesCategories, []).map((category) => category.key);
    expect(readPeopleView(params, keys).type).toBe('customer');
    expect(readPeopleView(params, TYPE_KEYS).type).toBe('all');
  });

  it('ignores a type while no categories are known yet', () => {
    expect(readPeopleView(new URLSearchParams('type=vc'), []).type).toBe('all');
  });

  it('works with a single category of its own', () => {
    const keys = singleCategory.map((category) => category.key);
    expect(readPeopleView(new URLSearchParams('type=member'), keys).type).toBe('member');
  });
});

describe('writePeopleView', () => {
  it('survives a round trip through the address', () => {
    const chosen = view({ type: 'network', status: 'gone_quiet', waiting: 'them', due: 'chase' });
    expect(readPeopleView(writePeopleView(chosen), TYPE_KEYS)).toEqual(chosen);
  });

  it('writes the "active" status group as status=active', () => {
    expect(writePeopleView({ ...DEFAULT_VIEW, status: 'active' }).toString()).toBe(
      'status=active',
    );
  });

  it('leaves the defaults out so the plain address stays clean', () => {
    expect(writePeopleView(DEFAULT_VIEW).toString()).toBe('');
  });
});

describe('clearFilters', () => {
  it('clears every filter but keeps the order', () => {
    const chosen = view({ type: 'vc', status: 'closed', waiting: 'nobody', due: 'overdue' });
    expect(clearFilters(chosen)).toEqual({ ...DEFAULT_VIEW, sort: 'name' });
  });
});

describe('applyPeopleView — other profiles', () => {
  it('filters a five-category profile by its own keys', () => {
    const people = peopleWithCategories(['prospect', 'customer', 'partner', 'referrer']);
    const rows = applyPeopleView(people, view({ type: 'partner' }));
    expect(rows).toHaveLength(3);
    expect(rows.every((row) => row.person_type === 'partner')).toBe(true);
  });

  it('filters a one-category profile', () => {
    const people = peopleWithCategories(['member', 'unknown']);
    expect(applyPeopleView(people, view({ type: 'member' }))).toHaveLength(6);
    expect(applyPeopleView(people, view({ type: 'unknown' }))).toHaveLength(6);
  });
});

describe('applyPeopleView — one filter at a time', () => {
  it('shows everyone by default', () => {
    expect(applyPeopleView(samplePeople, view({}))).toHaveLength(12);
  });

  it.each([
    ['startup', 5],
    ['vc', 3],
    ['network', 3],
    ['unknown', 1],
  ] as const)('keeps only the %s contacts', (type, expected) => {
    const rows = applyPeopleView(samplePeople, view({ type }));
    expect(rows).toHaveLength(expected);
    expect(rows.every((row) => row.person_type === type)).toBe(true);
  });

  it('keeps only one status', () => {
    const rows = applyPeopleView(samplePeople, view({ status: 'gone_quiet' }));
    expect(names(rows)).toEqual(['Elin Sato', 'Kira Novak']);
  });

  it('keeps the three running statuses when "active" is picked', () => {
    const rows = applyPeopleView(samplePeople, view({ status: 'active' }));
    expect(names(rows)).toEqual([
      'Ana Ruiz',
      'Carla Mendes',
      'Dan Weiss',
      'Greta Lind',
      'Ines Gallo',
      'Jonas Berg',
    ]);
  });

  it('leaves out people with no status when "active" is picked', () => {
    const notAssessed = { ...samplePeople[0]!, person_id: 'p-99', status: null };
    const rows = applyPeopleView([notAssessed], view({ status: 'active' }));
    expect(rows).toEqual([]);
  });

  it('keeps only the people the assistant has not looked at yet', () => {
    const notAssessed = { ...samplePeople[0]!, person_id: 'p-99', status: null };
    const rows = applyPeopleView([...samplePeople, notAssessed], view({ status: 'none' }));
    expect(rows.map((row) => row.person_id)).toEqual(['p-99']);
  });

  it('keeps only the people waiting on the owner', () => {
    const rows = applyPeopleView(samplePeople, view({ waiting: 'me' }));
    expect(names(rows)).toEqual(['Ana Ruiz', 'Dan Weiss', 'Elin Sato', 'Ines Gallo']);
  });

  it('keeps only the replies the owner owes when "overdue" is picked', () => {
    const rows = applyPeopleView(samplePeople, view({ due: 'overdue' }));
    expect(names(rows)).toEqual(['Dan Weiss', 'Elin Sato']);
  });

  it('keeps only the people to chase when "time to chase" is picked', () => {
    const rows = applyPeopleView(samplePeople, view({ due: 'chase' }));
    expect(names(rows)).toEqual(['Kira Novak']);
  });
});

describe('applyPeopleView — filters combine', () => {
  const base = samplePeople[0]!;
  const row = (id: string, changes: Partial<PeopleOverviewRow>): PeopleOverviewRow => ({
    ...base,
    person_id: id,
    full_name: id,
    ...changes,
  });
  const rows = [
    row('match', { person_type: 'vc', status: 'in_conversation', waiting_on: 'me' }),
    row('wrong-type', { person_type: 'startup', status: 'in_conversation', waiting_on: 'me' }),
    row('wrong-status', { person_type: 'vc', status: 'meeting_planned', waiting_on: 'me' }),
    row('wrong-waiting', { person_type: 'vc', status: 'in_conversation', waiting_on: 'them' }),
  ];

  it('keeps only the rows that match type, status and waiting-on together', () => {
    const chosen = view({ type: 'vc', status: 'in_conversation', waiting: 'me' });
    expect(names(applyPeopleView(rows, chosen))).toEqual(['match']);
  });

  it('adds the due filter on top of the others', () => {
    const chosen = view({ type: 'vc', status: 'in_conversation', waiting: 'me', due: 'overdue' });
    expect(applyPeopleView(rows, chosen)).toEqual([]);
  });
});

describe('applyPeopleView — sorting', () => {
  it('sorts by most recent contact first', () => {
    const rows = applyPeopleView(samplePeople, view({ sort: 'last-contact' }));
    expect(rows[0]?.full_name).toBe('Ana Ruiz');
    expect(rows.at(-1)?.full_name).toBe('Liam Doyle');
  });

  it('sorts by due date with the people who have no date last', () => {
    const rows = applyPeopleView(samplePeople, view({ sort: 'due-date' }));
    expect(rows[0]?.due_date).toBe('2026-03-01');
    expect(rows.at(-1)?.due_date).toBeNull();
  });

  it('does not change the list it was given', () => {
    const before = samplePeople.map((row) => row.person_id);
    applyPeopleView(samplePeople, view({}));
    expect(samplePeople.map((row) => row.person_id)).toEqual(before);
  });
});
