import { beforeEach, describe, expect, it } from 'vitest';
import { fetchCategories } from '../api/categories';
import { addCategory, removeCategory, RemovalOutcome, updateCategory } from '../api/categoryEdits';
import { fetchCategorySuggestions } from '../api/categorySuggestions';
import { fetchUpcomingMeetings } from '../api/meetings';
import { clearOverride, fetchOverride, markPersonAsNoise, saveOverride } from '../api/overrides';
import { fetchPeople } from '../api/people';
import { fetchPerson, fetchPersonConversations } from '../api/person';
import { answerReviewItem, fetchOpenReviewItems } from '../api/review';
import { fetchRunSince, requestRefresh } from '../api/refresh';
import { fetchRecentRuns } from '../api/runs';
import { fetchStatusLabels } from '../api/statusLabels';
import { fixedClock } from '../lib/clock';
import { RefusalReason, RefusedError } from '../lib/errors';
import { getSupabaseClient, isConfigured } from '../lib/supabaseClient';
import { DEMO_REFRESH_SECONDS } from '../constants/dashboard';
import { DEMO_OWNER_EMAIL, DEMO_UNUSED_CATEGORY } from './demoData';
import { startDemo } from './startDemo';

/** A Tuesday mid-morning, so "today", "overdue" and "this week" are all fixed. */
const DEMO_NOW = new Date(2026, 8, 29, 10, 0);
const clock = fixedClock(DEMO_NOW);

beforeEach(() => {
  startDemo(clock);
});

// Every read below goes through the real data layer, which checks the answer
// against the same schemas it checks the real database's answers against.
describe('demo data — the same contracts as the real database', () => {
  it('lists the invented people with their contact history', async () => {
    const people = await fetchPeople();
    expect(people).toHaveLength(14);
    expect(people.every((person) => person.message_count > 0)).toBe(true);
    const lastContacts = people.map((person) => person.last_contact_at ?? '');
    expect(lastContacts).toEqual([...lastContacts].sort().reverse());
  });

  it('files nobody under the category the owner has not added', async () => {
    const people = await fetchPeople();
    expect(people.some((person) => person.person_type === DEMO_UNUSED_CATEGORY)).toBe(false);
  });

  it('has overdue replies and people to chase', async () => {
    const people = await fetchPeople();
    expect(people.filter((person) => person.is_overdue).length).toBeGreaterThanOrEqual(2);
    expect(people.filter((person) => person.is_chase_due).length).toBeGreaterThanOrEqual(2);
  });

  it('uses the sales-outreach categories, stage names and suggestions', async () => {
    const keys = (await fetchCategories()).map((category) => category.key);
    expect(keys).toEqual(['prospect', 'customer', 'partner', 'unknown']);
    const suggestions = (await fetchCategorySuggestions()).map((suggestion) => suggestion.key);
    expect(suggestions).toHaveLength(4);
    expect(suggestions).toContain(DEMO_UNUSED_CATEGORY);
    const labels = await fetchStatusLabels();
    expect(labels.find((label) => label.status === 'in_process')?.label).toBe('In a deal');
  });

  it('has meetings in the coming week, soonest first', async () => {
    const meetings = await fetchUpcomingMeetings(DEMO_NOW);
    expect(meetings.map((meeting) => meeting.people?.full_name)).toEqual([
      'Daniel Novak',
      'Maya Lindqvist',
      'Kwame Mensah',
    ]);
  });

  it('reads one person and their timeline, and nobody for an unknown id', async () => {
    expect((await fetchPerson('demo-p01'))?.full_name).toBe('Maya Lindqvist');
    expect(await fetchPerson('nobody')).toBeNull();
    const conversations = await fetchPersonConversations('demo-p01');
    expect(conversations.map((conversation) => conversation.channel)).toEqual([
      'email',
      'calendar',
    ]);
  });

  it('has open questions, a correction and a run history, newest first', async () => {
    expect(await fetchOpenReviewItems()).toHaveLength(3);
    expect((await fetchOverride('demo-p02'))?.note).toMatch(/Thursday/);
    const runs = await fetchRecentRuns();
    expect(runs.map((run) => run.status)).toEqual(['success', 'partial', 'success']);
  });

  it('only uses addresses on the reserved .example domain', async () => {
    const conversations = await Promise.all(
      (await fetchPeople()).map((person) => fetchPersonConversations(person.person_id)),
    );
    const senders = conversations
      .flat()
      .flatMap((conversation) => conversation.messages)
      .map((message) => message.sender_identifier ?? '')
      .filter((sender) => sender.includes('@'));
    expect(senders.length).toBeGreaterThan(0);
    expect(senders.every((sender) => sender.endsWith('.example'))).toBe(true);
  });
});

describe('demo data — changes last for the page load only', () => {
  it('applies a correction to the person and removes it again', async () => {
    await saveOverride({
      person_id: 'demo-p03',
      status: 'closed',
      waiting_on: 'nobody',
      next_action: null,
      due_date: null,
      person_type: 'customer',
      note: 'Signed at the meetup.',
    });
    const corrected = await fetchPerson('demo-p03');
    expect(corrected).toMatchObject({
      status: 'closed',
      person_type: 'customer',
      has_override: true,
    });

    await clearOverride('demo-p03');
    expect(await fetchPerson('demo-p03')).toMatchObject({ status: 'contacted_no_reply' });
  });

  it('drops an answered question and a person marked as noise', async () => {
    await answerReviewItem('demo-r01', 'yes', DEMO_NOW);
    expect(await fetchOpenReviewItems()).toHaveLength(2);
    await markPersonAsNoise('demo-p14');
    expect(await fetchPeople()).toHaveLength(13);
  });

  it('adds, renames and removes categories with the database rules', async () => {
    const investor = {
      key: 'investor',
      label: 'Investor',
      group_label: 'Investors',
      description: '',
      colour: 'cyan' as const,
      sort_order: 50,
    };
    await addCategory(investor);
    await expect(addCategory(investor)).rejects.toEqual(
      new RefusedError(RefusalReason.Duplicate, 'categories.add'),
    );
    await expect(updateCategory('investor', { label: 'x'.repeat(41) })).rejects.toBeInstanceOf(
      RefusedError,
    );
    expect(await removeCategory('investor', DEMO_NOW)).toBe(RemovalOutcome.Deleted);
    expect(await removeCategory('partner', DEMO_NOW)).toBe(RemovalOutcome.Archived);
    const partner = (await fetchCategories()).find((category) => category.key === 'partner');
    expect(partner?.archived_at).toBe(DEMO_NOW.toISOString());
  });

  it('starts from the invented data again on the next load', async () => {
    await markPersonAsNoise('demo-p01');
    startDemo(clock);
    expect(await fetchPeople()).toHaveLength(14);
  });
});

describe('demo sign-in', () => {
  it('counts as configured and starts signed in as the demo owner', async () => {
    expect(isConfigured()).toBe(true);
    const { data } = await getSupabaseClient().auth.getSession();
    expect(data.session?.user.email).toBe(DEMO_OWNER_EMAIL);
  });
});

describe('demo "Refresh now"', () => {
  it('starts a pretend run that finishes a few seconds later', async () => {
    let now = DEMO_NOW;
    startDemo({ now: () => now });

    const outcome = await requestRefresh();
    expect(outcome).toEqual({ kind: 'started', requestedAt: DEMO_NOW, target: null });
    await expect(fetchRunSince(DEMO_NOW)).resolves.toMatchObject({
      status: 'running',
      trigger: 'refresh',
    });
    await expect(requestRefresh()).resolves.toMatchObject({
      kind: 'refused',
      code: 'already_running',
    });

    now = new Date(DEMO_NOW.getTime() + DEMO_REFRESH_SECONDS * 1_000);
    await expect(fetchRunSince(DEMO_NOW)).resolves.toMatchObject({ status: 'success' });
    const [newest] = await fetchRecentRuns();
    expect(newest?.run_step_logs.some((step) => step.step === 'summary_email')).toBe(false);
  });
});
