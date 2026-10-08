import type { ConversationWithMessages, RunWithSteps } from '../api/schemas';
import type {
  Category,
  CategoryColour,
  CategoryKey,
  CategorySuggestion,
  ContactStatus,
  PersonNoteRow,
  PersonOverrideRow,
  Relevance,
  ReviewItemRow,
  RunStatus,
  RunStep,
  Signal,
  StatusLabel,
  WaitingOn,
} from '../types/database';
import { atLocal, dailyRunEnd, dailyRunStart, hoursBefore, localDate } from './demoCalendar';
import { buildDemoNotes } from './demoNotes';
import { DEMO_PEOPLE, type PersonSeed, type ThreadSeed } from './demoPeople';

/**
 * The demo's whole database, built fresh from "now" on every page load, so
 * nothing a visitor changes outlives the tab.
 */

/** A person as the `people` table holds them, with the organisation's name inlined. */
export interface DemoPerson {
  id: string;
  full_name: string;
  role_title: string | null;
  organisation_name: string | null;
  person_type: CategoryKey;
  relevance: Relevance;
}

/** The assistant's latest judgement of one person (the `person_states` table). */
export interface DemoState {
  person_id: string;
  status: ContactStatus;
  waiting_on: WaitingOn;
  next_action: string;
  due_date: string | null;
  summary: string;
  signal: Signal;
  confidence: number;
  assessed_at: string;
}

export interface DemoTables {
  people: DemoPerson[];
  states: DemoState[];
  conversations: ConversationWithMessages[];
  overrides: PersonOverrideRow[];
  notes: PersonNoteRow[];
  categories: Category[];
  suggestions: CategorySuggestion[];
  statusLabels: StatusLabel[];
  reviewItems: ReviewItemRow[];
  runs: RunWithSteps[];
}

/** The sign-in address of the invented owner. */
export const DEMO_OWNER_EMAIL = 'owner@demo.example';

const CONFIDENCE = 0.85;
const RESERVED_SORT_ORDER = 1000;
/** Gaps between positions, as the database seeds them, so one can slot in between. */
const SORT_STEP = 10;

function category(
  key: CategoryKey,
  label: string,
  groupLabel: string,
  colour: CategoryColour,
  description: string,
): CategorySuggestion {
  return { key, label, group_label: groupLabel, colour, description };
}

/** The sales-outreach preset's categories, as `profile/presets/sales_outreach.toml` has them. */
const SALES_PRESET: readonly CategorySuggestion[] = [
  category('prospect', 'Prospect', 'Prospects', 'violet', 'Someone who might buy but has not yet.'),
  category('customer', 'Customer', 'Customers', 'teal', 'Someone whose organisation pays you.'),
  category('partner', 'Partner', 'Partners', 'indigo', 'Someone you sell with rather than to.'),
  category('referrer', 'Referrer', 'Referrers', 'orange', 'Someone who introduces you to buyers.'),
];

/**
 * The preset category the invented owner has not added, so the Settings page
 * shows a one-tap suggestion. Nobody in the demo is filed under it.
 */
export const DEMO_UNUSED_CATEGORY: CategoryKey = 'referrer';

const UNKNOWN_CATEGORY: Category = {
  ...category('unknown', 'Not known', 'Not known', 'grey', 'Not sorted yet.'),
  sort_order: RESERVED_SORT_ORDER,
  archived_at: null,
};

const SALES_STAGES: readonly StatusLabel[] = [
  { status: 'contacted_no_reply', label: 'Contacted, no reply yet' },
  { status: 'in_conversation', label: 'In conversation' },
  { status: 'meeting_planned', label: 'Meeting planned' },
  { status: 'in_process', label: 'In a deal' },
  { status: 'gone_quiet', label: 'Gone quiet' },
  { status: 'closed', label: 'Closed' },
];

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z]+/g, '');
}

function senderFor(seed: PersonSeed, thread: ThreadSeed): string {
  const first = slug(seed.fullName.split(' ')[0] ?? seed.fullName);
  if (thread.channel === 'linkedin') return slug(seed.fullName);
  return `${first}@${slug(seed.organisation ?? seed.fullName)}.example`;
}

function buildThread(
  seed: PersonSeed,
  thread: ThreadSeed,
  index: number,
  now: Date,
): ConversationWithMessages {
  const id = `${seed.id}-c${index}`;
  const stamps = { created_at: atLocal(now, -30, 8), updated_at: dailyRunStart(now) };
  const messages = thread.messages.map(([daysAgo, direction, body], position) => ({
    ...stamps,
    id: `${id}-m${position}`,
    conversation_id: id,
    source_message_id: `${id}-source-${position}`,
    direction,
    sent_at: atLocal(now, -daysAgo, 9 + position, 15),
    sender_identifier: direction === 'outbound' ? 'owner' : senderFor(seed, thread),
    body,
  }));
  const sentAt = (direction: string) =>
    messages.filter((message) => message.direction === direction).at(-1)?.sent_at ?? null;
  const meeting = thread.meeting;
  return {
    ...stamps,
    id,
    person_id: seed.id,
    channel: thread.channel,
    source_conversation_id: `${id}-source`,
    subject: thread.subject,
    relevance: 'relevant',
    relevance_decided_by: 'ai',
    first_message_at: messages[0]?.sent_at ?? null,
    last_message_at: messages.at(-1)?.sent_at ?? null,
    last_inbound_at: sentAt('inbound'),
    last_outbound_at: sentAt('outbound'),
    meeting_at: meeting ? atLocal(now, meeting.inDays, meeting.hour, meeting.minute) : null,
    messages,
  };
}

function buildState(seed: PersonSeed, now: Date): DemoState {
  return {
    person_id: seed.id,
    status: seed.status,
    waiting_on: seed.waitingOn,
    next_action: seed.nextAction,
    due_date: seed.dueInDays === null ? null : localDate(now, seed.dueInDays),
    summary: seed.summary,
    signal: seed.signal,
    confidence: CONFIDENCE,
    assessed_at: dailyRunStart(now),
  };
}

function buildOverrides(now: Date): PersonOverrideRow[] {
  const stamp = hoursBefore(now, 30);
  return [
    {
      id: 'demo-o01',
      created_at: stamp,
      updated_at: stamp,
      person_id: 'demo-p02',
      status: 'in_process',
      waiting_on: 'me',
      next_action: 'Send the revised quote with the annual discount',
      due_date: localDate(now, -2),
      person_type: null,
      note: 'Finance meets on Thursday — the quote must reach him before then.',
    },
  ];
}

/**
 * Rafael Ortega's mailbox record, kept apart until the owner says they are the
 * same person. It is not on the list: the assistant is not sure about it yet,
 * and joining the two waits for the next daily run, as it does for real.
 */
const MAILBOX_ORTEGA: DemoPerson = {
  id: 'demo-p15',
  full_name: 'R. Ortega',
  role_title: null,
  organisation_name: null,
  person_type: 'unknown',
  relevance: 'unsure',
};

function reviewItem(
  now: Date,
  id: string,
  fields: Pick<ReviewItemRow, 'kind' | 'person_id' | 'other_person_id' | 'question'>,
): ReviewItemRow {
  const stamp = dailyRunStart(now);
  return {
    id,
    created_at: stamp,
    updated_at: stamp,
    conversation_id: null,
    answer: null,
    answered_at: null,
    ...fields,
  };
}

function buildReviewItems(now: Date): ReviewItemRow[] {
  return [
    reviewItem(now, 'demo-r01', {
      kind: 'relevance',
      person_id: 'demo-p14',
      other_person_id: null,
      question: 'Is Marcus Bell part of your sales outreach?',
    }),
    reviewItem(now, 'demo-r02', {
      kind: 'same_person',
      person_id: 'demo-p08',
      other_person_id: MAILBOX_ORTEGA.id,
      question:
        'Are Rafael Ortega on LinkedIn and R. Ortega in your mailbox the same person?',
    }),
    reviewItem(now, 'demo-r03', {
      kind: 'relevance',
      person_id: 'demo-p12',
      other_person_id: null,
      question: 'Is Leila Haddad part of your sales outreach?',
    }),
  ];
}

type StepSeed = readonly [
  step: RunStep,
  status: RunStatus,
  found: number,
  added: number,
  errorCode?: string,
];

function buildRun(id: string, started: string, steps: readonly StepSeed[]): RunWithSteps {
  const failed = steps.some(([, status]) => status === 'failed');
  return {
    id,
    created_at: started,
    updated_at: started,
    started_at: started,
    finished_at: dailyRunEnd(started),
    status: failed ? 'partial' : 'success',
    trigger: 'cloud',
    run_step_logs: steps.map(([step, status, found, added, errorCode], index) => ({
      id: `${id}-s${index}`,
      created_at: started,
      updated_at: started,
      run_id: id,
      step,
      status,
      items_found: status === 'failed' ? null : found,
      items_new: status === 'failed' ? null : added,
      error_code: errorCode ?? null,
      error_detail: null,
    })),
  };
}

function buildRuns(now: Date): RunWithSteps[] {
  return [0, 1, 2].map((day) =>
    buildRun(`demo-run-${day}`, dailyRunStart(now, day), [
      ['collect_linkedin', 'success', 18 - day * 3, 4 - day],
      day === 1
        ? ['collect_email', 'failed', 0, 0, 'source_unavailable']
        : ['collect_email', 'success', 42 - day * 5, 6 - day],
      ['collect_calendar', 'success', 5, 1],
      ['assess', 'success', 14, 9 - day * 2],
      ['summary_email', 'success', 1, 1],
    ]),
  );
}

/** Builds the demo's tables around `now`. */
export function createDemoData(now: Date): DemoTables {
  return {
    people: [
      ...DEMO_PEOPLE.map((seed) => ({
        id: seed.id,
        full_name: seed.fullName,
        role_title: seed.role,
        organisation_name: seed.organisation,
        person_type: seed.type,
        relevance: seed.relevance,
      })),
      { ...MAILBOX_ORTEGA },
    ],
    states: DEMO_PEOPLE.map((seed) => buildState(seed, now)),
    conversations: DEMO_PEOPLE.flatMap((seed) =>
      seed.threads.map((thread, index) => buildThread(seed, thread, index, now)),
    ),
    overrides: buildOverrides(now),
    notes: buildDemoNotes(now),
    categories: [
      ...SALES_PRESET.filter((preset) => preset.key !== DEMO_UNUSED_CATEGORY).map(
        (preset, index) => ({
          ...preset,
          sort_order: (index + 1) * SORT_STEP,
          archived_at: null,
        }),
      ),
      UNKNOWN_CATEGORY,
    ],
    suggestions: [...SALES_PRESET],
    statusLabels: [...SALES_STAGES],
    reviewItems: buildReviewItems(now),
    runs: buildRuns(now),
  };
}
