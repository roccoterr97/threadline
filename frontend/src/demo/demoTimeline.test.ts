import { describe, expect, it } from 'vitest';
import { fetchUpcomingMeetings } from '../api/meetings';
import { fetchPeople } from '../api/people';
import { fetchPersonConversations } from '../api/person';
import { fetchOpenReviewItems } from '../api/review';
import { fetchRecentRuns } from '../api/runs';
import { fixedClock } from '../lib/clock';
import { startDemo } from './startDemo';

/**
 * The demo is built around whatever "now" the visitor arrives at. Whatever
 * the hour, nothing it shows may have happened in the future, and every read
 * must pass the same schemas the real database's answers do.
 */

const MOMENTS = [
  new Date(2026, 9, 4, 0, 5),
  new Date(2026, 9, 4, 4, 59),
  new Date(2026, 9, 4, 5, 1),
  new Date(2026, 9, 4, 5, 59),
  new Date(2026, 9, 4, 6, 0),
  new Date(2026, 9, 4, 23, 59),
  new Date(2027, 2, 28, 3, 0),
  new Date(2030, 0, 1, 12, 0),
];

function notAfter(stamp: string | null, now: Date): boolean {
  return stamp === null || new Date(stamp).getTime() <= now.getTime();
}

describe.each(MOMENTS)('the demo opened at %s', (now) => {
  it('shows no message, contact or assessment from the future', async () => {
    startDemo(fixedClock(now));
    const people = await fetchPeople();
    expect(people.length).toBeGreaterThan(0);
    for (const person of people) {
      expect(notAfter(person.last_contact_at, now), person.person_id).toBe(true);
      expect(notAfter(person.assessed_at, now), person.person_id).toBe(true);
      const conversations = await fetchPersonConversations(person.person_id);
      const late = conversations
        .flatMap((conversation) => conversation.messages)
        .filter((message) => !notAfter(message.sent_at, now));
      expect(late).toEqual([]);
    }
  });

  it('shows no run that started or finished in the future', async () => {
    startDemo(fixedClock(now));
    const runs = await fetchRecentRuns();
    expect(runs.length).toBeGreaterThan(0);
    const late = runs.filter(
      (run) => !notAfter(run.started_at, now) || !notAfter(run.finished_at, now),
    );
    expect(late).toEqual([]);
  });

  it('reads the questions and the meetings coming up', async () => {
    startDemo(fixedClock(now));
    await expect(fetchOpenReviewItems()).resolves.not.toHaveLength(0);
    await expect(fetchUpcomingMeetings(now)).resolves.toBeInstanceOf(Array);
  });
});
