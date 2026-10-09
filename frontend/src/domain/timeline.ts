import type { ConversationWithMessages } from '../api/schemas';
import {
  MESSAGE_FOLD_CHARACTERS,
  MESSAGE_FOLD_LINES,
  TIMELINE_MESSAGE_LIMIT,
} from '../constants/dashboard';
import type { Channel, Direction } from '../types/database';

/** One message, ready to render, with the conversation context it needs. */
export interface TimelineEntry {
  id: string;
  channel: Channel;
  direction: Direction;
  sentAt: string;
  subject: string | null;
  body: string | null;
}

/**
 * Flattens a person's conversations into one list across every channel,
 * newest message first — the order the owner reads a history in.
 */
export function buildTimeline(
  conversations: readonly ConversationWithMessages[],
): TimelineEntry[] {
  return conversations
    .flatMap((conversation) =>
      conversation.messages.map<TimelineEntry>((message) => ({
        id: message.id,
        channel: conversation.channel,
        direction: message.direction,
        sentAt: message.sent_at,
        subject: conversation.subject,
        body: message.body,
      })),
    )
    .sort((a, b) => new Date(b.sentAt).getTime() - new Date(a.sentAt).getTime());
}

/**
 * True when a conversation reached the message limit, so older messages of it
 * may be missing from the history.
 */
export function timelineIsCut(conversations: readonly ConversationWithMessages[]): boolean {
  return conversations.some((conversation) => conversation.messages.length >= TIMELINE_MESSAGE_LIMIT);
}

/** A message's opening, and whether anything was left out to make it. */
export interface MessagePreview {
  preview: string;
  isFolded: boolean;
}

/** Below this share of the limit, a cut mid-word beats losing most of the last line. */
const MIN_WORD_CUT_SHARE = 0.6;

const ELLIPSIS = '…';

function cutAtWord(text: string, maxCharacters: number): string {
  if (text.length <= maxCharacters) return text;
  const cut = text.slice(0, maxCharacters);
  if (/\s/.test(text.charAt(maxCharacters))) return cut;
  const lastSpace = cut.search(/\s\S*$/);
  return lastSpace >= maxCharacters * MIN_WORD_CUT_SHARE ? cut.slice(0, lastSpace) : cut;
}

/**
 * The first few lines of a long message, so one long email does not push the
 * rest of the history off the screen. A message within both limits is
 * returned whole and unfolded.
 */
export function previewMessage(
  body: string,
  maxLines: number = MESSAGE_FOLD_LINES,
  maxCharacters: number = MESSAGE_FOLD_CHARACTERS,
): MessagePreview {
  const whole = body.trimEnd();
  const firstLines = whole.split('\n').slice(0, maxLines).join('\n');
  const opening = cutAtWord(firstLines, maxCharacters).trimEnd();
  if (opening.length >= whole.length) return { preview: whole, isFolded: false };
  return { preview: `${opening}${ELLIPSIS}`, isFolded: true };
}
