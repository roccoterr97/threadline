import { beforeEach, describe, expect, it } from 'vitest';
import { fetchPeople } from '../api/people';
import { fetchPerson } from '../api/person';
import { answerReviewItem, fetchOpenReviewItems } from '../api/review';
import { fixedClock } from '../lib/clock';
import type { ReviewAnswer } from '../types/database';
import { createDemoData, type DemoTables } from './demoData';
import { DemoDatabase, type RowFilter } from './demoDatabase';
import { startDemo } from './startDemo';

/**
 * The demo's review questions behave as the real database's do: a relevance
 * answer changes the person at once (migration 0007's trigger), and a
 * "same person?" question always names two stored people (migration 0001's
 * `review_items_same_person_needs_other` check).
 */

const DEMO_NOW = new Date(2026, 8, 29, 10, 0);
const clock = fixedClock(DEMO_NOW);
const MARCUS = 'demo-p14';
const LEILA = 'demo-p12';
const RAFAEL = 'demo-p08';

/** Picks the row with this id, as `.eq('id', id)` does. */
function withId(id: string): RowFilter {
  return (row) => 'id' in row && row.id === id;
}

async function listedIds(): Promise<string[]> {
  return (await fetchPeople()).map((person) => person.person_id);
}

describe('demo relevance questions, through the dashboard', () => {
  beforeEach(() => {
    startDemo(clock);
  });

  it('ask only about people who are not on the list yet', async () => {
    const asked = (await fetchOpenReviewItems())
      .filter((item) => item.kind === 'relevance')
      .map((item) => item.person_id);
    expect(asked).toEqual([MARCUS, LEILA]);
    const listed = await listedIds();
    expect(asked.filter((id) => id !== null && listed.includes(id))).toEqual([]);
  });

  it('add the person to the list when the answer is "Yes"', async () => {
    await answerReviewItem('demo-r01', 'yes', DEMO_NOW);
    expect(await listedIds()).toContain(MARCUS);
    expect((await fetchPerson(MARCUS))?.full_name).toBe('Marcus Bell');
  });

  it('keep the person off the list when the answer is "No"', async () => {
    const before = await listedIds();
    await answerReviewItem('demo-r03', 'no', DEMO_NOW);
    expect(await listedIds()).toEqual(before);
    expect(await fetchOpenReviewItems()).toHaveLength(2);
  });

  it('take the person off the list again when a "Yes" is changed to "No"', async () => {
    await answerReviewItem('demo-r01', 'yes', DEMO_NOW);
    await answerReviewItem('demo-r01', 'no', DEMO_NOW);
    expect(await listedIds()).not.toContain(MARCUS);
    expect(await fetchPerson(MARCUS)).toBeNull();
  });
});

describe('demo relevance answers, in the stored tables', () => {
  let tables: DemoTables;
  let database: DemoDatabase;

  beforeEach(() => {
    tables = createDemoData(DEMO_NOW);
    database = new DemoDatabase(tables, clock);
  });

  function answer(itemId: string, value: ReviewAnswer) {
    return database.update('review_items', withId(itemId), {
      answer: value,
      answered_at: DEMO_NOW.toISOString(),
    });
  }

  function relevanceOf(personId: string) {
    return tables.people.find((person) => person.id === personId)?.relevance;
  }

  it('makes the person relevant on "Yes" and noise on "No", as the trigger does', () => {
    expect(answer('demo-r01', 'yes').error).toBeNull();
    expect(answer('demo-r03', 'no').error).toBeNull();
    expect(relevanceOf(MARCUS)).toBe('relevant');
    expect(relevanceOf(LEILA)).toBe('noise');
  });

  it('follows a changed answer', () => {
    answer('demo-r01', 'yes');
    answer('demo-r01', 'no');
    expect(relevanceOf(MARCUS)).toBe('noise');
  });

  it('leaves the person alone when the same answer is saved again', () => {
    answer('demo-r01', 'yes');
    database.update('people', withId(MARCUS), { relevance: 'noise' });
    answer('demo-r01', 'yes');
    expect(relevanceOf(MARCUS)).toBe('noise');
  });

  it('changes nobody else', () => {
    const others = () => tables.people.filter((person) => person.id !== MARCUS);
    const before = others();
    answer('demo-r01', 'no');
    expect(others()).toEqual(before);
  });

  it('does not touch anyone for a "same person?" answer', () => {
    const before = tables.people;
    expect(answer('demo-r02', 'yes').error).toBeNull();
    expect(tables.people).toEqual(before);
  });
});

describe('the demo "same person?" question', () => {
  it('names a second stored person who is not on the list', async () => {
    const tables = createDemoData(DEMO_NOW);
    const question = tables.reviewItems.find((item) => item.kind === 'same_person');
    expect(question?.person_id).toBe(RAFAEL);
    const other = tables.people.find((person) => person.id === question?.other_person_id);
    expect(other).toMatchObject({ full_name: 'R. Ortega', relevance: 'unsure' });
    startDemo(clock);
    expect(await listedIds()).not.toContain(other?.id);
  });

  it('closes on "Yes" and leaves the list as it was until the next daily run', async () => {
    startDemo(clock);
    const before = await fetchPeople();
    await answerReviewItem('demo-r02', 'yes', DEMO_NOW);
    const open = (await fetchOpenReviewItems()).map((item) => item.id);
    expect(open).toEqual(['demo-r01', 'demo-r03']);
    expect(await fetchPeople()).toEqual(before);
  });
});
