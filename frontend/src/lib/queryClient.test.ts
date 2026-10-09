import { focusManager, QueryObserver, type QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QUERY_STALE_TIME_MS } from '../constants/dashboard';
import { NotAllowedError, NotSignedInError } from './errors';
import { createQueryClient } from './queryClient';

/** Watches one query the way a mounted screen does, so focus can refetch it. */
function watch(client: QueryClient, queryFn: () => Promise<string>) {
  const observer = new QueryObserver(client, { queryKey: ['overdue'], queryFn });
  return observer.subscribe(() => undefined);
}

/** The tab goes to the background and comes back, as a phone does overnight. */
async function leaveAndReturn(): Promise<void> {
  focusManager.setFocused(false);
  focusManager.setFocused(true);
  await vi.advanceTimersByTimeAsync(0);
}

let client: QueryClient;
let stopWatching: () => void;
let queryFn: ReturnType<typeof vi.fn<() => Promise<string>>>;

beforeEach(async () => {
  vi.useFakeTimers();
  client = createQueryClient();
  // The provider does this in the app; it is what listens for the tab coming back.
  client.mount();
  queryFn = vi.fn(() => Promise.resolve('monday'));
  stopWatching = watch(client, queryFn);
  await vi.advanceTimersByTimeAsync(0);
});

afterEach(() => {
  stopWatching();
  client.unmount();
  client.clear();
  focusManager.setFocused(undefined);
  vi.useRealTimers();
});

describe('createQueryClient — a tab that was left open', () => {
  it('fetches again when the page becomes visible after the data went stale', async () => {
    expect(queryFn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(QUERY_STALE_TIME_MS + 1);
    await leaveAndReturn();
    expect(queryFn).toHaveBeenCalledTimes(2);
  });

  it('leaves fresh data alone, so a quick switch back and forth costs nothing', async () => {
    await vi.advanceTimersByTimeAsync(QUERY_STALE_TIME_MS - 1_000);
    await leaveAndReturn();
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it('keeps showing the old answer while the new one is on its way', async () => {
    queryFn.mockReturnValue(new Promise(() => undefined));
    await vi.advanceTimersByTimeAsync(QUERY_STALE_TIME_MS + 1);
    await leaveAndReturn();
    const state = client.getQueryState(['overdue']);
    expect(state?.fetchStatus).toBe('fetching');
    expect(state?.data).toBe('monday');
  });
});

describe('createQueryClient — retrying a failed read', () => {
  const retry = (error: unknown, failures = 0) => {
    const option = createQueryClient().getDefaultOptions().queries?.retry;
    if (typeof option !== 'function') throw new Error('retry should be a function');
    return option(failures, error as Error);
  };

  it.each([new NotSignedInError('x'), new NotAllowedError('x')])(
    'does not retry %s, which a second try cannot fix',
    (error) => {
      expect(retry(error)).toBe(false);
    },
  );

  it('retries an ordinary failure', () => {
    expect(retry(new Error('network'))).toBe(true);
  });
});
