import type { ConversationWithMessages, RunWithSteps } from '../../api/schemas';
import type {
  Category,
  CategoryColour,
  CategoryKey,
  Channel,
  ContactStatus,
  PeopleOverviewRow,
  PersonOverrideRow,
  ReviewItemRow,
  Signal,
  StatusLabel,
  UpcomingMeetingRow,
  WaitingOn,
} from '../../types/database';

/**
 * Made-up data shaped like Plan 1's `backend/tests/fixtures/sample_data.json`.
 *
 * Same shape and same spread as that file — twelve people covering startup,
 * investor and network, every status, both channels, two unanswered questions
 * and two runs of which the newest failed — but written here as typed rows of
 * the `people_overview` view, which is what the dashboard actually reads. The
 * names and messages are different inventions; none of them are real.
 */

/** A live category, written on one line. */
export function category(
  key: CategoryKey,
  label: string,
  groupLabel: string,
  colour: CategoryColour,
  sortOrder: number,
): Category {
  return {
    key,
    label,
    group_label: groupLabel,
    description: `People who are a ${label.toLowerCase()} to the owner.`,
    colour,
    sort_order: sortOrder,
    archived_at: null,
  };
}

/**
 * The job-search preset the database seeds: the same categories, names,
 * colours and order the dashboard showed before categories became data.
 */
export const sampleCategories: Category[] = [
  category('startup', 'Startup', 'Startups', 'violet', 10),
  category('vc', 'Investor', 'Investors', 'cyan', 20),
  category('network', 'Network', 'Network', 'orange', 30),
  category('unknown', 'Not known', 'Unknown', 'grey', 1000),
];

/** A sales profile: four categories of its own, then the reserved one. */
export const salesCategories: Category[] = [
  category('prospect', 'Prospect', 'Prospects', 'violet', 10),
  category('customer', 'Customer', 'Customers', 'teal', 20),
  category('partner', 'Partner', 'Partners', 'indigo', 30),
  category('referrer', 'Referrer', 'Referrers', 'pink', 40),
  category('unknown', 'Not known', 'Unknown', 'grey', 1000),
];

/** The smallest profile: one category of its own, then the reserved one. */
export const singleCategory: Category[] = [
  category('member', 'Member', 'Members', 'olive', 10),
  category('unknown', 'Not known', 'Unknown', 'grey', 1000),
];

/** When the fixtures' archived categories were retired. */
export const ARCHIVED_AT = '2026-03-01T00:00:00.000Z';

/** The same list with the category `key` archived. */
export function withArchived(categories: readonly Category[], key: CategoryKey): Category[] {
  return categories.map((category) =>
    category.key === key ? { ...category, archived_at: ARCHIVED_AT } : category,
  );
}

/** The status names the job-search preset seeds. */
export const sampleStatusLabels: StatusLabel[] = [
  { status: 'contacted_no_reply', label: 'Contacted, no reply yet' },
  { status: 'in_conversation', label: 'In conversation' },
  { status: 'meeting_planned', label: 'Meeting planned' },
  { status: 'in_process', label: 'In a hiring process' },
  { status: 'gone_quiet', label: 'Gone quiet' },
  { status: 'closed', label: 'Closed' },
];

/**
 * Twelve people spread over `keys` round-robin, keeping every other field of
 * the sample people — for screens tested against a different profile.
 */
export function peopleWithCategories(keys: readonly CategoryKey[]): PeopleOverviewRow[] {
  return samplePeople.map((person, index) => ({
    ...person,
    person_type: keys[index % keys.length] ?? person.person_type,
  }));
}

/** Fixed so the "26 hours" rule and every relative date are reproducible. */
export const NOW = new Date('2026-03-12T09:00:00.000Z');

const TIMESTAMPS = {
  created_at: '2026-02-01T08:00:00.000Z',
  updated_at: '2026-03-11T08:00:00.000Z',
};

interface PersonSeed {
  id: string;
  full_name: string;
  role_title: string;
  organisation_name: string | null;
  person_type: CategoryKey;
  status: ContactStatus;
  waiting_on: WaitingOn;
  signal: Signal;
  last_contact_at: string;
  due_date: string | null;
  is_overdue: boolean;
  is_chase_due: boolean;
  channels: Channel[];
  message_count: number;
  has_override: boolean;
}

const SEEDS: PersonSeed[] = [
  {
    id: 'p-01',
    full_name: 'Ana Ruiz',
    role_title: 'Co-founder',
    organisation_name: 'Northwind Labs',
    person_type: 'startup',
    status: 'in_conversation',
    waiting_on: 'me',
    signal: 'positive',
    last_contact_at: '2026-03-11T16:20:00.000Z',
    due_date: '2026-03-14',
    is_overdue: false,
    is_chase_due: false,
    channels: ['linkedin'],
    message_count: 6,
    has_override: false,
  },
  {
    id: 'p-02',
    full_name: 'Ben Okafor',
    role_title: 'Head of Engineering',
    organisation_name: 'Palegreen',
    person_type: 'startup',
    status: 'contacted_no_reply',
    waiting_on: 'them',
    signal: 'neutral',
    last_contact_at: '2026-03-09T10:05:00.000Z',
    due_date: '2026-03-16',
    is_overdue: false,
    is_chase_due: false,
    channels: ['email'],
    message_count: 1,
    has_override: false,
  },
  {
    id: 'p-03',
    full_name: 'Carla Mendes',
    role_title: 'Talent Partner',
    organisation_name: 'Brightfield Ventures',
    person_type: 'vc',
    status: 'meeting_planned',
    waiting_on: 'them',
    signal: 'positive',
    last_contact_at: '2026-03-10T14:40:00.000Z',
    due_date: '2026-03-18',
    is_overdue: false,
    is_chase_due: false,
    channels: ['linkedin', 'email'],
    message_count: 9,
    has_override: false,
  },
  {
    id: 'p-04',
    full_name: 'Dan Weiss',
    role_title: 'Former colleague',
    organisation_name: null,
    person_type: 'network',
    status: 'in_process',
    waiting_on: 'me',
    signal: 'positive',
    last_contact_at: '2026-03-05T09:15:00.000Z',
    due_date: '2026-03-09',
    is_overdue: true,
    is_chase_due: false,
    channels: ['email'],
    message_count: 12,
    has_override: true,
  },
  {
    id: 'p-05',
    full_name: 'Elin Sato',
    role_title: 'Chief of Staff',
    organisation_name: 'Harbourline',
    person_type: 'startup',
    status: 'gone_quiet',
    waiting_on: 'me',
    signal: 'cold',
    last_contact_at: '2026-02-18T11:00:00.000Z',
    due_date: '2026-03-02',
    is_overdue: true,
    is_chase_due: false,
    channels: ['linkedin'],
    message_count: 4,
    has_override: false,
  },
  {
    id: 'p-06',
    full_name: 'Farid Haddad',
    role_title: 'Principal',
    organisation_name: 'Kestrel Capital',
    person_type: 'vc',
    status: 'closed',
    waiting_on: 'nobody',
    signal: 'cold',
    last_contact_at: '2026-02-02T13:30:00.000Z',
    due_date: null,
    is_overdue: false,
    is_chase_due: false,
    channels: ['email'],
    message_count: 3,
    has_override: false,
  },
  {
    id: 'p-07',
    full_name: 'Greta Lind',
    role_title: 'Friend',
    organisation_name: null,
    person_type: 'network',
    status: 'in_conversation',
    waiting_on: 'them',
    signal: 'positive',
    last_contact_at: '2026-03-11T07:45:00.000Z',
    due_date: '2026-03-20',
    is_overdue: false,
    is_chase_due: false,
    channels: ['linkedin', 'email'],
    message_count: 15,
    has_override: false,
  },
  {
    id: 'p-08',
    full_name: 'Hugo Prieto',
    role_title: 'Founder',
    organisation_name: 'Slate & Sons',
    person_type: 'startup',
    status: 'contacted_no_reply',
    waiting_on: 'them',
    signal: 'neutral',
    last_contact_at: '2026-03-08T18:10:00.000Z',
    due_date: '2026-03-15',
    is_overdue: false,
    is_chase_due: false,
    channels: ['linkedin'],
    message_count: 1,
    has_override: false,
  },
  {
    id: 'p-09',
    full_name: 'Ines Gallo',
    role_title: 'People Lead',
    organisation_name: 'Rowan Partners',
    person_type: 'vc',
    status: 'in_process',
    waiting_on: 'me',
    signal: 'positive',
    last_contact_at: '2026-03-11T12:00:00.000Z',
    due_date: '2026-03-13',
    is_overdue: false,
    is_chase_due: false,
    channels: ['email'],
    message_count: 8,
    has_override: false,
  },
  {
    id: 'p-10',
    full_name: 'Jonas Berg',
    role_title: 'Mentor',
    organisation_name: null,
    person_type: 'network',
    status: 'meeting_planned',
    waiting_on: 'nobody',
    signal: 'neutral',
    last_contact_at: '2026-03-07T15:25:00.000Z',
    due_date: null,
    is_overdue: false,
    is_chase_due: false,
    channels: ['linkedin'],
    message_count: 5,
    has_override: false,
  },
  {
    id: 'p-11',
    full_name: 'Kira Novak',
    role_title: 'VP Product',
    organisation_name: 'Duskwell',
    person_type: 'startup',
    status: 'gone_quiet',
    waiting_on: 'them',
    signal: 'cold',
    last_contact_at: '2026-02-20T08:55:00.000Z',
    due_date: '2026-03-01',
    is_overdue: false,
    is_chase_due: true,
    channels: ['linkedin', 'email'],
    message_count: 7,
    has_override: false,
  },
  {
    id: 'p-12',
    full_name: 'Liam Doyle',
    role_title: 'Recruiter',
    organisation_name: 'Ashford Search',
    person_type: 'unknown',
    status: 'closed',
    waiting_on: 'nobody',
    signal: 'neutral',
    last_contact_at: '2026-01-28T09:00:00.000Z',
    due_date: null,
    is_overdue: false,
    is_chase_due: false,
    channels: ['email'],
    message_count: 2,
    has_override: false,
  },
];

export const samplePeople: PeopleOverviewRow[] = SEEDS.map((seed) => ({
  person_id: seed.id,
  full_name: seed.full_name,
  role_title: seed.role_title,
  organisation_name: seed.organisation_name,
  person_type: seed.person_type,
  status: seed.status,
  waiting_on: seed.waiting_on,
  next_action: `Follow up with ${seed.full_name.split(' ')[0] ?? 'them'}`,
  due_date: seed.due_date,
  summary: `${seed.full_name} was introduced through the job search.`,
  signal: seed.signal,
  confidence: 0.8,
  assessed_at: '2026-03-12T05:03:00.000Z',
  last_contact_at: seed.last_contact_at,
  channels: seed.channels,
  message_count: seed.message_count,
  is_overdue: seed.is_overdue,
  has_override: seed.has_override,
  is_chase_due: seed.is_chase_due,
}));

/** The person used in the person-page tests. */
export function samplePerson(id = 'p-01'): PeopleOverviewRow {
  const found = samplePeople.find((row) => row.person_id === id);
  if (found === undefined) throw new Error(`No sample person with id ${id}`);
  return found;
}

export const sampleOverride: PersonOverrideRow = {
  ...TIMESTAMPS,
  id: 'ov-04',
  person_id: 'p-04',
  status: 'in_process',
  waiting_on: 'me',
  next_action: 'Send the take-home task back',
  due_date: '2026-03-09',
  person_type: 'network',
  note: 'He asked me to chase him if it goes quiet.',
};

/** Ana's history: a LinkedIn thread, an email thread and one calendar meeting. */
export const sampleConversations: ConversationWithMessages[] = [
  {
    ...TIMESTAMPS,
    id: 'c-01',
    person_id: 'p-01',
    channel: 'linkedin',
    source_conversation_id: 'li-thread-1',
    subject: null,
    relevance: 'relevant',
    relevance_decided_by: 'rule',
    first_message_at: '2026-03-02T09:00:00.000Z',
    last_message_at: '2026-03-11T16:20:00.000Z',
    last_inbound_at: '2026-03-11T16:20:00.000Z',
    last_outbound_at: '2026-03-02T09:00:00.000Z',
    meeting_at: null,
    messages: [
      {
        ...TIMESTAMPS,
        id: 'm-01',
        conversation_id: 'c-01',
        source_message_id: 'li-1',
        direction: 'outbound',
        sent_at: '2026-03-02T09:00:00.000Z',
        sender_identifier: 'owner',
        body: 'Hello Ana, I liked what Northwind is building. Could we talk?',
      },
      {
        ...TIMESTAMPS,
        id: 'm-02',
        conversation_id: 'c-01',
        source_message_id: 'li-2',
        direction: 'inbound',
        sent_at: '2026-03-11T16:20:00.000Z',
        sender_identifier: 'ana',
        body: 'Happy to. Does Friday morning suit you?',
      },
    ],
  },
  {
    ...TIMESTAMPS,
    id: 'c-02',
    person_id: 'p-01',
    channel: 'email',
    source_conversation_id: 'mail-thread-1',
    subject: 'Intro call',
    relevance: 'relevant',
    relevance_decided_by: 'ai',
    first_message_at: '2026-03-06T10:00:00.000Z',
    last_message_at: '2026-03-06T10:00:00.000Z',
    last_inbound_at: null,
    last_outbound_at: '2026-03-06T10:00:00.000Z',
    meeting_at: null,
    messages: [
      {
        ...TIMESTAMPS,
        id: 'm-03',
        conversation_id: 'c-02',
        source_message_id: 'mail-1',
        direction: 'outbound',
        sent_at: '2026-03-06T10:00:00.000Z',
        sender_identifier: 'owner',
        body: 'Sending over the notes we spoke about.',
      },
    ],
  },
  {
    ...TIMESTAMPS,
    id: 'c-03',
    person_id: 'p-01',
    channel: 'calendar',
    source_conversation_id: 'cal-event-1',
    subject: 'Coffee with Ana (Northwind)',
    relevance: 'relevant',
    relevance_decided_by: 'rule',
    first_message_at: '2026-03-09T08:30:00.000Z',
    last_message_at: '2026-03-09T08:30:00.000Z',
    last_inbound_at: '2026-03-09T08:30:00.000Z',
    last_outbound_at: null,
    meeting_at: '2026-03-13T10:00:00.000Z',
    messages: [
      {
        ...TIMESTAMPS,
        id: 'm-04',
        conversation_id: 'c-03',
        source_message_id: 'cal-event-1-v1',
        direction: 'inbound',
        sent_at: '2026-03-09T08:30:00.000Z',
        sender_identifier: 'ana@northwind.example',
        body: 'Meeting on 13 Mar, 10:00 to 10:30, organised by Ana. You accepted.',
      },
    ],
  },
];

/** Three meetings in the week after NOW, soonest first, as the query returns them. */
export const sampleMeetings: UpcomingMeetingRow[] = [
  {
    id: 'c-03',
    subject: 'Coffee with Ana (Northwind)',
    meeting_at: '2026-03-13T10:00:00.000Z',
    person_id: 'p-01',
    people: { full_name: 'Ana Ruiz', organisations: { name: 'Northwind Labs' } },
  },
  {
    id: 'c-21',
    subject: 'Intro with Brightfield',
    meeting_at: '2026-03-16T14:30:00.000Z',
    person_id: 'p-03',
    people: { full_name: 'Carla Mendes', organisations: { name: 'Brightfield Ventures' } },
  },
  {
    id: 'c-22',
    subject: null,
    meeting_at: '2026-03-18T08:00:00.000Z',
    person_id: 'p-10',
    people: { full_name: 'Jonas Berg', organisations: null },
  },
];

export const sampleReviewItems: ReviewItemRow[] = [
  {
    ...TIMESTAMPS,
    id: 'r-01',
    kind: 'relevance',
    person_id: 'p-08',
    conversation_id: 'c-08',
    other_person_id: null,
    question: 'Is the thread with Hugo Prieto about a job?',
    answer: null,
    answered_at: null,
  },
  {
    ...TIMESTAMPS,
    id: 'r-02',
    kind: 'same_person',
    person_id: 'p-03',
    conversation_id: null,
    other_person_id: 'p-09',
    question: 'Are Carla Mendes on LinkedIn and C. Mendes in your mailbox the same person?',
    answer: null,
    answered_at: null,
  },
];

/** Two runs: the newest one failed, the one before it worked. */
export const sampleRuns: RunWithSteps[] = [
  {
    ...TIMESTAMPS,
    id: 'run-02',
    started_at: '2026-03-12T05:00:00.000Z',
    finished_at: '2026-03-12T05:02:10.000Z',
    status: 'failed',
    trigger: 'cloud',
    run_step_logs: [
      {
        ...TIMESTAMPS,
        id: 'rs-03',
        run_id: 'run-02',
        step: 'collect_linkedin',
        status: 'success',
        items_found: 12,
        items_new: 3,
        error_code: null,
        error_detail: null,
      },
      {
        ...TIMESTAMPS,
        id: 'rs-04',
        run_id: 'run-02',
        step: 'collect_email',
        status: 'failed',
        items_found: null,
        items_new: null,
        error_code: 'source_auth_failed',
        error_detail: 'mailbox sign-in was refused',
      },
    ],
  },
  {
    ...TIMESTAMPS,
    id: 'run-01',
    started_at: '2026-03-11T05:00:00.000Z',
    finished_at: '2026-03-11T05:04:00.000Z',
    status: 'success',
    trigger: 'cloud',
    run_step_logs: [
      {
        ...TIMESTAMPS,
        id: 'rs-01',
        run_id: 'run-01',
        step: 'collect_linkedin',
        status: 'success',
        items_found: 20,
        items_new: 5,
        error_code: null,
        error_detail: null,
      },
      {
        ...TIMESTAMPS,
        id: 'rs-05',
        run_id: 'run-01',
        step: 'collect_calendar',
        status: 'success',
        items_found: 4,
        items_new: 1,
        error_code: null,
        error_detail: null,
      },
      {
        ...TIMESTAMPS,
        id: 'rs-02',
        run_id: 'run-01',
        step: 'assess',
        status: 'success',
        items_found: 12,
        items_new: 12,
        error_code: null,
        error_detail: null,
      },
    ],
  },
];
