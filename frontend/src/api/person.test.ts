import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TIMELINE_MESSAGE_LIMIT } from '../constants/dashboard';
import { getSupabaseClient } from '../lib/supabaseClient';
import { sampleConversations } from '../test/__fixtures__/sampleData';
import { fetchPersonConversations } from './person';
import type { ConversationWithMessages } from './schemas';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

type Call = [method: string, ...args: unknown[]];

/** A stand-in for the Supabase query builder that records every call and answers with `data`. */
function fakeClient(data: unknown) {
  const calls: Call[] = [];
  const builder: Record<string, unknown> = {
    then: (resolve: (value: unknown) => void) => {
      resolve({ data, error: null, status: 200 });
    },
  };
  for (const method of ['from', 'select', 'eq', 'order', 'limit']) {
    builder[method] = (...args: unknown[]) => {
      calls.push([method, ...args]);
      return builder;
    };
  }
  return { client: builder, calls };
}

/** What the database sends back when asked for the newest messages first. */
function newestFirst(conversation: ConversationWithMessages): ConversationWithMessages {
  return { ...conversation, messages: [...conversation.messages].reverse() };
}

const BUSY = sampleConversations[0]!;

let calls: Call[];

function answerWith(data: unknown) {
  const fake = fakeClient(data);
  calls = fake.calls;
  vi.mocked(getSupabaseClient).mockReturnValue(
    fake.client as unknown as ReturnType<typeof getSupabaseClient>,
  );
}

beforeEach(() => {
  answerWith([newestFirst(BUSY)]);
});

describe('fetchPersonConversations', () => {
  it('asks for the newest messages first, so a cap drops the oldest', async () => {
    await fetchPersonConversations('p-01');
    expect(calls).toContainEqual(['order', 'sent_at', { referencedTable: 'messages', ascending: false }]);
    expect(calls).toContainEqual(['limit', TIMELINE_MESSAGE_LIMIT, { referencedTable: 'messages' }]);
  });

  it('hands the messages back oldest first, as the page expects them', async () => {
    const [conversation] = await fetchPersonConversations('p-01');
    expect(conversation?.messages.map((message) => message.id)).toEqual(
      BUSY.messages.map((message) => message.id),
    );
  });

  it('does not change the shape of a conversation without messages', async () => {
    answerWith([{ ...BUSY, messages: [] }]);
    const [conversation] = await fetchPersonConversations('p-01');
    expect(conversation?.messages).toEqual([]);
  });
});
