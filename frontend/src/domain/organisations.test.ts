import { describe, expect, it } from 'vitest';
import { samplePeople, samplePerson } from '../test/__fixtures__/sampleData';
import type { PeopleOverviewRow } from '../types/database';
import {
  applyOrganisationsView,
  clearOrganisationFilters,
  DEFAULT_ORGANISATION_SORT,
  findOrganisation,
  isAssessed,
  organisationNameOf,
  readOrganisationsView,
  summariseOrganisations,
  writeOrganisationsView,
  type OrganisationsView,
} from './organisations';
import { DEFAULT_FILTERS } from './peopleView';

const DEFAULT_VIEW: OrganisationsView = { ...DEFAULT_FILTERS, sort: DEFAULT_ORGANISATION_SORT };

/** Ben (waiting on them) moved in with Ana (the owner's turn) at Northwind Labs. */
const NORTHWIND_OF_TWO: PeopleOverviewRow[] = [
  samplePerson('p-01'),
  { ...samplePerson('p-02'), organisation_name: 'Northwind Labs' },
];

/** The names in order; the group without one reads as null. */
function names(people: readonly PeopleOverviewRow[], view = DEFAULT_VIEW): (string | null)[] {
  return applyOrganisationsView(people, view).map((organisation) => organisation.name);
}

describe('the organisation a person is listed under', () => {
  it('is the name as written', () => {
    expect(organisationNameOf({ organisation_name: 'Acme' })).toBe('Acme');
  });

  it.each([null, '', '   '])('is none for %j', (organisation_name) => {
    expect(organisationNameOf({ organisation_name })).toBeNull();
  });
});

describe('summarising the organisations', () => {
  it('puts everyone at one organisation together, newest contact first', () => {
    const [northwind] = summariseOrganisations(NORTHWIND_OF_TWO);
    expect(northwind?.name).toBe('Northwind Labs');
    expect(northwind?.people.map((person) => person.person_id)).toEqual(['p-01', 'p-02']);
    expect(northwind?.lastContactAt).toBe('2026-03-11T16:20:00.000Z');
  });

  it('counts the headline numbers over that organisation alone', () => {
    const [northwind] = summariseOrganisations(NORTHWIND_OF_TWO);
    expect(northwind?.counters).toEqual({
      actionsForMe: 1,
      overdue: 0,
      timeToChase: 0,
      waitingOnThem: 1,
      activeConversations: 1,
    });
  });

  it('gathers the people with no organisation into one group', () => {
    const none = findOrganisation(samplePeople, null);
    expect(none?.people.map((person) => person.person_id)).toEqual(['p-07', 'p-10', 'p-04']);
  });

  it('finds an organisation by name and nothing for a name nobody has', () => {
    expect(findOrganisation(samplePeople, 'Northwind Labs')?.people).toHaveLength(1);
    expect(findOrganisation(samplePeople, 'Nowhere')).toBeNull();
  });

  it('knows whether the assistant has said who is waiting there', () => {
    const [northwind] = summariseOrganisations(NORTHWIND_OF_TWO);
    expect(isAssessed(northwind!)).toBe(true);
    const [unseen] = summariseOrganisations([{ ...samplePerson('p-01'), waiting_on: null }]);
    expect(isAssessed(unseen!)).toBe(false);
  });
});

describe('the order of the organisations', () => {
  it('puts the ones needing the owner first, then by last contact, with the group without last', () => {
    expect(names(samplePeople)).toEqual([
      'Harbourline',
      'Northwind Labs',
      'Rowan Partners',
      'Duskwell',
      'Brightfield Ventures',
      'Palegreen',
      'Slate & Sons',
      'Kestrel Capital',
      'Ashford Search',
      null,
    ]);
  });

  it('can go by most recent contact', () => {
    expect(names(samplePeople, { ...DEFAULT_VIEW, sort: 'last-contact' }).slice(0, 3)).toEqual([
      'Northwind Labs',
      'Rowan Partners',
      'Brightfield Ventures',
    ]);
  });

  it('can go by name', () => {
    expect(names(samplePeople, { ...DEFAULT_VIEW, sort: 'name' }).slice(0, 3)).toEqual([
      'Ashford Search',
      'Brightfield Ventures',
      'Duskwell',
    ]);
  });

  it('can go by how many people are there', () => {
    const people = [...NORTHWIND_OF_TWO, samplePerson('p-05')];
    expect(names(people, { ...DEFAULT_VIEW, sort: 'people' })).toEqual([
      'Northwind Labs',
      'Harbourline',
    ]);
  });

  it('keeps the group without an organisation last whatever the order', () => {
    expect(names(samplePeople, { ...DEFAULT_VIEW, sort: 'name' }).at(-1)).toBeNull();
    expect(names(samplePeople, { ...DEFAULT_VIEW, sort: 'people' }).at(-1)).toBeNull();
  });
});

describe('the filters on the organisations', () => {
  it('keeps an organisation when one of its people fits, and still counts everyone there', () => {
    const [northwind] = applyOrganisationsView(NORTHWIND_OF_TWO, {
      ...DEFAULT_VIEW,
      waiting: 'them',
    });
    expect(northwind?.name).toBe('Northwind Labs');
    expect(northwind?.people).toHaveLength(2);
    expect(northwind?.counters.actionsForMe).toBe(1);
  });

  it('drops an organisation where nobody fits every filter', () => {
    expect(names(samplePeople, { ...DEFAULT_VIEW, due: 'overdue' })).toEqual([
      'Harbourline',
      null,
    ]);
    expect(names(samplePeople, { ...DEFAULT_VIEW, type: 'vc', due: 'overdue' })).toEqual([]);
  });
});

describe('the organisations view in the address', () => {
  const typeKeys = ['startup', 'vc'];

  it('reads the filters and the order', () => {
    const params = new URLSearchParams('type=vc&waiting=me&sort=name');
    expect(readOrganisationsView(params, typeKeys)).toEqual({
      ...DEFAULT_FILTERS,
      type: 'vc',
      waiting: 'me',
      sort: 'name',
    });
  });

  it('falls back to the defaults for junk, including a People-only order', () => {
    const params = new URLSearchParams('type=robot&sort=due-date');
    expect(readOrganisationsView(params, typeKeys)).toEqual(DEFAULT_VIEW);
  });

  it('writes only what differs from the defaults', () => {
    expect(writeOrganisationsView(DEFAULT_VIEW).toString()).toBe('');
    expect(
      writeOrganisationsView({ ...DEFAULT_VIEW, due: 'chase', sort: 'people' }).toString(),
    ).toBe('due=chase&sort=people');
  });

  it('clears the filters but keeps the order', () => {
    expect(clearOrganisationFilters({ ...DEFAULT_VIEW, due: 'chase', sort: 'name' })).toEqual({
      ...DEFAULT_FILTERS,
      sort: 'name',
    });
  });
});
