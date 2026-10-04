/**
 * Database shape used by the dashboard.
 *
 * HAND-WRITTEN from the database contract in `docs/architecture.md` and the
 * files in `supabase/migrations/`, because the Supabase project did not exist
 * yet when the dashboard was built.
 *
 * REGENERATE THIS FILE once the real project exists:
 *
 *   supabase gen types typescript --project-id <project-id> > src/types/database.ts
 *
 * and re-run `npm run typecheck` — any mismatch between this file and the real
 * schema will surface there.
 */

export type Channel = 'linkedin' | 'email' | 'calendar';
export type Direction = 'inbound' | 'outbound';
/**
 * A category key (`categories.key`). Categories are data the owner defines,
 * so this is any string; the database's foreign key keeps it honest.
 */
export type CategoryKey = string;
/** The fixed palette slots a category may be drawn in (`categories.colour`). */
export type CategoryColour =
  | 'violet'
  | 'cyan'
  | 'orange'
  | 'pink'
  | 'indigo'
  | 'teal'
  | 'olive'
  | 'brown'
  | 'grey';
export type Relevance = 'relevant' | 'noise' | 'unsure';
export type ContactStatus =
  | 'contacted_no_reply'
  | 'in_conversation'
  | 'meeting_planned'
  | 'in_process'
  | 'gone_quiet'
  | 'closed';
export type WaitingOn = 'me' | 'them' | 'nobody';
export type Signal = 'positive' | 'neutral' | 'cold';
export type ReviewKind = 'relevance' | 'same_person';
export type ReviewAnswer = 'yes' | 'no';
export type RunStatus = 'running' | 'success' | 'partial' | 'failed';
export type RunStep =
  | 'collect_linkedin'
  | 'collect_email'
  | 'collect_calendar'
  | 'assess'
  | 'summary_email';

/** Columns every table carries. */
interface RowBase {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface OrganisationRow extends RowBase {
  name: string;
  kind: string | null;
  email_domain: string | null;
}

export interface PersonRow extends RowBase {
  full_name: string;
  person_type: CategoryKey;
  role_title: string | null;
  organisation_id: string | null;
  relevance: Relevance;
}

/**
 * One kind of person the owner tracks (the `categories` table). The dashboard
 * only reads it. An archived category may still sit on some people.
 */
export interface CategoryRow extends RowBase {
  key: CategoryKey;
  label: string;
  /** The plural, used for column heads and filter chips. */
  group_label: string;
  /** Written for the assistant; the dashboard does not show it. */
  description: string;
  colour: CategoryColour;
  sort_order: number;
  archived_at: string | null;
}

/** The columns of a category the dashboard reads. */
export type Category = Pick<
  CategoryRow,
  'key' | 'label' | 'group_label' | 'description' | 'colour' | 'sort_order' | 'archived_at'
>;

/** A new category, as the settings page inserts it (id and timestamps default). */
export type CategoryInsert = Omit<Category, 'archived_at'>;

/** What the settings page may change on an existing category. `key` never changes. */
export type CategoryChanges = Partial<Omit<Category, 'key'>>;

/**
 * A category the owner's chosen preset suggests (`category_suggestions`),
 * offered on the settings page as a one-tap addition. Written by the daily job.
 */
export interface CategorySuggestionRow extends RowBase {
  key: CategoryKey;
  label: string;
  group_label: string;
  description: string;
  colour: CategoryColour;
  sort_order: number;
}

/** The columns of a suggestion the dashboard reads. */
export type CategorySuggestion = Pick<
  CategorySuggestionRow,
  'key' | 'label' | 'group_label' | 'description' | 'colour'
>;

/** The on-screen name of one status (the `status_labels` table). */
export interface StatusLabelRow extends RowBase {
  status: ContactStatus;
  label: string;
}

/** The columns of a status label the dashboard reads. */
export type StatusLabel = Pick<StatusLabelRow, 'status' | 'label'>;

export interface ConversationRow extends RowBase {
  person_id: string | null;
  channel: Channel;
  source_conversation_id: string;
  subject: string | null;
  relevance: Relevance;
  relevance_decided_by: string | null;
  first_message_at: string | null;
  last_message_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  /** Calendar threads only: when the meeting starts. Null when cancelled or not a meeting. */
  meeting_at: string | null;
}

/**
 * A meeting in the "Coming up" strip: a calendar conversation with the name of
 * the person it is with and their organisation, embedded through the foreign
 * keys `conversations.person_id` and `people.organisation_id`.
 */
export interface UpcomingMeetingRow {
  id: string;
  subject: string | null;
  meeting_at: string;
  person_id: string | null;
  people: {
    full_name: string;
    organisations: { name: string } | null;
  } | null;
}

export interface MessageRow extends RowBase {
  conversation_id: string;
  source_message_id: string;
  direction: Direction;
  sent_at: string;
  sender_identifier: string | null;
  /** Null for messages judged to be noise — their text is never stored. */
  body: string | null;
}

export interface PersonOverrideRow extends RowBase {
  person_id: string;
  status: ContactStatus | null;
  waiting_on: WaitingOn | null;
  next_action: string | null;
  due_date: string | null;
  person_type: CategoryKey | null;
  note: string | null;
}

/** A note the owner typed on a person's page (the `person_notes` table). */
export interface PersonNoteRow extends RowBase {
  person_id: string;
  /** Plain text, never blank. The dashboard holds the same length limit as the database. */
  body: string;
}

/** A new note, as the person page inserts it (id and timestamps default). */
export type PersonNoteInsert = Pick<PersonNoteRow, 'person_id' | 'body'>;

export interface ReviewItemRow extends RowBase {
  kind: ReviewKind;
  person_id: string | null;
  conversation_id: string | null;
  other_person_id: string | null;
  question: string;
  answer: ReviewAnswer | null;
  answered_at: string | null;
}

export interface RunLogRow extends RowBase {
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  trigger: string;
}

export interface RunStepLogRow extends RowBase {
  run_id: string;
  step: RunStep;
  status: RunStatus;
  items_found: number | null;
  items_new: number | null;
  error_code: string | null;
  error_detail: string | null;
}

/**
 * The `people_overview` view: one row per relevant person, with the effective
 * values (the owner's override where one is set, otherwise the AI's assessment).
 *
 * Matches `supabase/migrations/0004_overdue_and_chase.sql`. Note the key column is
 * `person_id`, not `id`. The view already filters to relevant people, so it
 * carries no `relevance` column. Everything that comes from `person_states` is
 * nullable, because a person the assistant has not looked at yet has no row
 * there; the counts and flags are coalesced in SQL and so never arrive null.
 */
export interface PeopleOverviewRow {
  person_id: string;
  full_name: string;
  role_title: string | null;
  organisation_name: string | null;
  person_type: CategoryKey;
  status: ContactStatus | null;
  waiting_on: WaitingOn | null;
  next_action: string | null;
  due_date: string | null;
  summary: string | null;
  signal: Signal | null;
  confidence: number | null;
  assessed_at: string | null;
  last_contact_at: string | null;
  channels: Channel[];
  message_count: number;
  /** Due date passed and waiting on the owner: a reply the owner owes. */
  is_overdue: boolean;
  has_override: boolean;
  /** Due date passed and waiting on them: time to send a nudge. */
  is_chase_due: boolean;
}

/** Insert / update payload for a hand-made correction. */
export interface PersonOverrideWrite {
  person_id: string;
  status: ContactStatus | null;
  waiting_on: WaitingOn | null;
  next_action: string | null;
  due_date: string | null;
  person_type: CategoryKey | null;
  note: string | null;
}
