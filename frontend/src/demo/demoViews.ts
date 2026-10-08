import type { ConversationWithMessages } from '../api/schemas';
import type { Channel, PeopleOverviewRow, UpcomingMeetingRow } from '../types/database';
import type { DemoPerson, DemoTables } from './demoData';

/**
 * The demo's stand-ins for what the database computes: the `people_overview`
 * view and the embedded rows PostgREST adds to a conversation.
 */

interface ContactStats {
  last_contact_at: string | null;
  channels: Channel[];
  message_count: number;
}

function contactStats(conversations: readonly ConversationWithMessages[]): ContactStats {
  const sentAt = conversations.flatMap((conversation) =>
    conversation.messages.map((message) => message.sent_at),
  );
  const channels = new Set(
    conversations
      .filter((conversation) => conversation.messages.length > 0)
      .map((conversation) => conversation.channel),
  );
  return {
    last_contact_at: sentAt.length === 0 ? null : sentAt.reduce((a, b) => (a > b ? a : b)),
    channels: [...channels].sort(),
    message_count: sentAt.length,
  };
}

function overviewRow(tables: DemoTables, person: DemoPerson, today: string): PeopleOverviewRow {
  const state = tables.states.find((row) => row.person_id === person.id);
  const override = tables.overrides.find((row) => row.person_id === person.id);
  const waitingOn = override?.waiting_on ?? state?.waiting_on ?? null;
  const dueDate = override?.due_date ?? state?.due_date ?? null;
  const late = dueDate !== null && dueDate < today;
  const own = tables.conversations.filter((row) => row.person_id === person.id);
  return {
    person_id: person.id,
    full_name: person.full_name,
    role_title: person.role_title,
    organisation_name: person.organisation_name,
    person_type: override?.person_type ?? person.person_type,
    status: override?.status ?? state?.status ?? null,
    waiting_on: waitingOn,
    next_action: override?.next_action ?? state?.next_action ?? null,
    due_date: dueDate,
    summary: state?.summary ?? null,
    signal: state?.signal ?? null,
    confidence: state?.confidence ?? null,
    assessed_at: state?.assessed_at ?? null,
    ...contactStats(own),
    is_overdue: late && waitingOn === 'me',
    has_override: override !== undefined,
    is_chase_due: late && waitingOn === 'them',
  };
}

/** The `people_overview` view: relevant people, corrections winning over the assistant. */
export function peopleOverview(tables: DemoTables, today: string): PeopleOverviewRow[] {
  return tables.people
    .filter((person) => person.relevance === 'relevant')
    .map((person) => overviewRow(tables, person, today));
}

/** A conversation with its person and organisation embedded, as the meetings query reads it. */
type ConversationWithPerson = ConversationWithMessages & Pick<UpcomingMeetingRow, 'people'>;

/** Every conversation with its messages and its person embedded. */
export function conversationsWithPeople(tables: DemoTables): ConversationWithPerson[] {
  return tables.conversations.map((conversation) => {
    const person = tables.people.find((row) => row.id === conversation.person_id);
    const organisation = person?.organisation_name ?? null;
    return {
      ...conversation,
      people:
        person === undefined
          ? null
          : {
              full_name: person.full_name,
              relevance: person.relevance,
              organisations: organisation === null ? null : { name: organisation },
            },
    };
  });
}
