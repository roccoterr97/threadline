import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchRunSince, requestRefresh } from '../api/refresh';
import { REFRESH_WATCH_LIMIT_MINUTES } from '../constants/dashboard';
import { refreshIsBusy } from '../domain/refresh';
import { useRefreshNow } from './useRefreshNow';

vi.mock('../api/refresh', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/refresh')>()),
  requestRefresh: vi.fn(),
  fetchRunSince: vi.fn(),
}));

const requestRefreshMock = vi.mocked(requestRefresh);
const fetchRunSinceMock = vi.mocked(fetchRunSince);
const MS_PER_MINUTE = 60_000;
const WATCH_LIMIT_MS = REFRESH_WATCH_LIMIT_MINUTES * MS_PER_MINUTE;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-09T09:00:00Z'));
  requestRefreshMock.mockImplementation(() =>
    Promise.resolve({ kind: 'started', requestedAt: new Date(), target: 'github' }),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

async function startRefresh() {
  const hook = renderHook(() => useRefreshNow(), { wrapper });
  await act(async () => {
    hook.result.current.start();
    await vi.advanceTimersByTimeAsync(0);
  });
  return hook;
}

describe('useRefreshNow — a run that never shows up', () => {
  it('waits while the watch window is open', async () => {
    fetchRunSinceMock.mockResolvedValue(null);
    const { result } = await startRefresh();
    expect(result.current.status.kind).toBe('waiting');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(WATCH_LIMIT_MS - MS_PER_MINUTE);
    });
    expect(result.current.status.kind).toBe('waiting');
  });

  it('gives up and frees the button when the watch window ends', async () => {
    fetchRunSinceMock.mockResolvedValue(null);
    const { result } = await startRefresh();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(WATCH_LIMIT_MS + MS_PER_MINUTE);
    });
    expect(result.current.status.kind).toBe('timed_out');
    expect(refreshIsBusy(result.current.status)).toBe(false);
  });

  it('gives up on a run that is still going when the window ends', async () => {
    const stamp = new Date().toISOString();
    fetchRunSinceMock.mockResolvedValue({
      id: 'run-1',
      created_at: stamp,
      updated_at: stamp,
      started_at: stamp,
      finished_at: null,
      status: 'running',
      trigger: 'refresh',
    });
    const { result } = await startRefresh();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(WATCH_LIMIT_MS + MS_PER_MINUTE);
    });
    expect(result.current.status.kind).toBe('timed_out');
  });

  it('stops the end-of-window timer when the button goes away', async () => {
    fetchRunSinceMock.mockResolvedValue(null);
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');
    const { unmount } = await startRefresh();
    const windowTimerIndex = setTimeoutSpy.mock.calls.findIndex(
      ([, delay]) => typeof delay === 'number' && delay > WATCH_LIMIT_MS - MS_PER_MINUTE,
    );
    expect(windowTimerIndex).toBeGreaterThanOrEqual(0);
    const windowTimer: unknown = setTimeoutSpy.mock.results[windowTimerIndex]?.value;
    unmount();
    expect(clearTimeoutSpy).toHaveBeenCalledWith(windowTimer);
  });
});
