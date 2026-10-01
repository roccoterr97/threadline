import { z } from 'zod';
import type {
  Category,
  CategorySuggestion,
  ConversationRow,
  MessageRow,
  PeopleOverviewRow,
  PersonOverrideRow,
  ReviewItemRow,
  RunLogRow,
  RunStepLogRow,
  StatusLabel,
  UpcomingMeetingRow,
} from '../types/database';

/**
 * Runtime shape of everything that crosses the network boundary.
 *
 * Each schema is checked against its hand-written type with `satisfies`, so the
 * two can never drift apart without a type error.
 */

export const channelSchema = z.enum(['linkedin', 'email', 'calendar']);
export const directionSchema = z.enum(['inbound', 'outbound']);
/** Same rule as the database's check on `categories.key`. */
export const categoryKeySchema = z.string().regex(/^[a-z][a-z0-9_]{0,30}$/);
export const categoryColourSchema = z.enum([
  'violet',
  'cyan',
  'orange',
  'pink',
  'indigo',
  'teal',
  'olive',
  'brown',
  'grey',
]);
export const relevanceSchema = z.enum(['relevant', 'noise', 'unsure']);
export const contactStatusSchema = z.enum([
  'contacted_no_reply',
  'in_conversation',
  'meeting_planned',
  'in_process',
  'gone_quiet',
  'closed',
]);
export const waitingOnSchema = z.enum(['me', 'them', 'nobody']);
export const signalSchema = z.enum(['positive', 'neutral', 'cold']);
export const reviewKindSchema = z.enum(['relevance', 'same_person']);
export const reviewAnswerSchema = z.enum(['yes', 'no']);
export const runStatusSchema = z.enum(['running', 'success', 'partial', 'failed']);
export const runStepSchema = z.enum([
  'collect_linkedin',
  'collect_email',
  'collect_calendar',
  'assess',
  'summary_email',
]);

const timestamp = z.string();
const nullableTimestamp = z.string().nullable();

const rowBase = {
  id: z.string(),
  created_at: timestamp,
  updated_at: timestamp,
};

export const peopleOverviewRowSchema = z.object({
  person_id: z.string(),
  full_name: z.string(),
  role_title: z.string().nullable(),
  organisation_name: z.string().nullable(),
  person_type: categoryKeySchema,
  status: contactStatusSchema.nullable(),
  waiting_on: waitingOnSchema.nullable(),
  next_action: z.string().nullable(),
  due_date: z.string().nullable(),
  summary: z.string().nullable(),
  signal: signalSchema.nullable(),
  confidence: z.number().nullable(),
  assessed_at: nullableTimestamp,
  last_contact_at: nullableTimestamp,
  channels: z.array(channelSchema),
  message_count: z.number(),
  is_overdue: z.boolean(),
  has_override: z.boolean(),
  is_chase_due: z.boolean(),
}) satisfies z.ZodType<PeopleOverviewRow>;

/** Same length limits as the database's checks on the category text columns. */
const categoryLabel = z.string().min(1).max(40);
const categoryDescription = z.string().max(1000);

export const categorySchema = z.object({
  key: categoryKeySchema,
  label: categoryLabel,
  group_label: categoryLabel,
  description: categoryDescription,
  colour: categoryColourSchema,
  sort_order: z.number().int(),
  archived_at: nullableTimestamp,
}) satisfies z.ZodType<Category>;

export const categorySuggestionSchema = z.object({
  key: categoryKeySchema,
  label: categoryLabel,
  group_label: categoryLabel,
  description: categoryDescription,
  colour: categoryColourSchema,
}) satisfies z.ZodType<CategorySuggestion>;

export const statusLabelSchema = z.object({
  status: contactStatusSchema,
  label: z.string().min(1),
}) satisfies z.ZodType<StatusLabel>;

export const messageRowSchema = z.object({
  ...rowBase,
  conversation_id: z.string(),
  source_message_id: z.string(),
  direction: directionSchema,
  sent_at: timestamp,
  sender_identifier: z.string().nullable(),
  body: z.string().nullable(),
}) satisfies z.ZodType<MessageRow>;

export const conversationRowSchema = z.object({
  ...rowBase,
  person_id: z.string().nullable(),
  channel: channelSchema,
  source_conversation_id: z.string(),
  subject: z.string().nullable(),
  relevance: relevanceSchema,
  relevance_decided_by: z.string().nullable(),
  first_message_at: nullableTimestamp,
  last_message_at: nullableTimestamp,
  last_inbound_at: nullableTimestamp,
  last_outbound_at: nullableTimestamp,
  meeting_at: nullableTimestamp,
}) satisfies z.ZodType<ConversationRow>;

export const upcomingMeetingRowSchema = z.object({
  id: z.string(),
  subject: z.string().nullable(),
  meeting_at: timestamp,
  person_id: z.string().nullable(),
  people: z
    .object({
      full_name: z.string(),
      organisations: z.object({ name: z.string() }).nullable(),
    })
    .nullable(),
}) satisfies z.ZodType<UpcomingMeetingRow>;

/** A conversation with its messages, as the timeline query returns it. */
export const conversationWithMessagesSchema = conversationRowSchema.extend({
  messages: z.array(messageRowSchema),
});

export type ConversationWithMessages = z.infer<typeof conversationWithMessagesSchema>;

export const personOverrideRowSchema = z.object({
  ...rowBase,
  person_id: z.string(),
  status: contactStatusSchema.nullable(),
  waiting_on: waitingOnSchema.nullable(),
  next_action: z.string().nullable(),
  due_date: z.string().nullable(),
  person_type: categoryKeySchema.nullable(),
  note: z.string().nullable(),
}) satisfies z.ZodType<PersonOverrideRow>;

export const reviewItemRowSchema = z.object({
  ...rowBase,
  kind: reviewKindSchema,
  person_id: z.string().nullable(),
  conversation_id: z.string().nullable(),
  other_person_id: z.string().nullable(),
  question: z.string(),
  answer: reviewAnswerSchema.nullable(),
  answered_at: nullableTimestamp,
}) satisfies z.ZodType<ReviewItemRow>;

export const runStepLogRowSchema = z.object({
  ...rowBase,
  run_id: z.string(),
  step: runStepSchema,
  status: runStatusSchema,
  items_found: z.number().nullable(),
  items_new: z.number().nullable(),
  error_code: z.string().nullable(),
  error_detail: z.string().nullable(),
}) satisfies z.ZodType<RunStepLogRow>;

export const runLogRowSchema = z.object({
  ...rowBase,
  started_at: timestamp,
  finished_at: nullableTimestamp,
  status: runStatusSchema,
  trigger: z.string(),
}) satisfies z.ZodType<RunLogRow>;

/** A run with its steps, as the run-history query returns it. */
export const runWithStepsSchema = runLogRowSchema.extend({
  run_step_logs: z.array(runStepLogRowSchema),
});

export type RunWithSteps = z.infer<typeof runWithStepsSchema>;
