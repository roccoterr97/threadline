import { describe, expect, it } from 'vitest';
import { TIMELINE_MESSAGE_LIMIT } from '../constants/dashboard';
import { sampleConversations } from '../test/__fixtures__/sampleData';
import { previewMessage, timelineIsCut } from './timeline';

describe('previewMessage', () => {
  it('leaves a short message whole', () => {
    expect(previewMessage('Happy to. Does Friday suit you?')).toEqual({
      preview: 'Happy to. Does Friday suit you?',
      isFolded: false,
    });
  });

  it('does not fold a message that is exactly at the line limit', () => {
    const body = ['1', '2', '3'].join('\n');
    expect(previewMessage(body, 3, 400).isFolded).toBe(false);
  });

  it('ignores trailing blank lines', () => {
    expect(previewMessage('One\nTwo\n\n\n', 2, 400).isFolded).toBe(false);
  });

  it('keeps only the first lines of a message with many lines', () => {
    const body = ['1', '2', '3', '4'].join('\n');
    expect(previewMessage(body, 2, 400)).toEqual({ preview: '1\n2…', isFolded: true });
  });

  it('cuts a long single paragraph at the last whole word', () => {
    const body = 'alpha beta gamma delta epsilon';
    expect(previewMessage(body, 6, 14)).toEqual({ preview: 'alpha beta…', isFolded: true });
  });

  it('keeps a word that ends exactly at the limit', () => {
    expect(previewMessage('alpha beta gamma', 6, 10).preview).toBe('alpha beta…');
  });

  it('cuts mid-word rather than lose most of the text to one long word', () => {
    const body = `ab ${'x'.repeat(30)}`;
    expect(previewMessage(body, 6, 10).preview).toBe(`ab ${'x'.repeat(7)}…`);
  });
});

describe('timelineIsCut', () => {
  const conversationOf = (messageCount: number) => ({
    ...sampleConversations[0]!,
    messages: Array.from({ length: messageCount }, () => sampleConversations[0]!.messages[0]!),
  });

  it('is true once a conversation reaches the message limit', () => {
    expect(timelineIsCut([conversationOf(TIMELINE_MESSAGE_LIMIT)])).toBe(true);
  });

  it('is true when only one of several conversations is that long', () => {
    expect(timelineIsCut([conversationOf(2), conversationOf(TIMELINE_MESSAGE_LIMIT)])).toBe(true);
  });

  it('is false while every conversation is below the limit', () => {
    expect(timelineIsCut([conversationOf(TIMELINE_MESSAGE_LIMIT - 1), conversationOf(0)])).toBe(false);
    expect(timelineIsCut([])).toBe(false);
  });
});
