import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { fetchRunSince, refreshRunQueryKey, requestRefresh } from '../api/refresh';
import { REFRESH_DONE_SHOWN_MS } from '../constants/dashboard';
import {
  nextCheckDelay,
  refreshProgress,
  refusalStatus,
  type RefreshOutcome,
  type RefreshStatus,
  watchTimeLeftMs,
} from '../domain/refresh';
import { useClock } from '../lib/ClockContext';

export interface RefreshNow {
  status: RefreshStatus;
  start: () => void;
}

type StartedOutcome = Extract<RefreshOutcome, { kind: 'started' }>;

/** Watches the run a started refresh set off, until it ends or the watch limit passes. */
function useRefreshWatch(started: StartedOutcome | null) {
  const clock = useClock();
  const requestedAt = started?.requestedAt ?? null;
  const [, setWatchChecks] = useState(0);
  const watch = useQuery({
    queryKey: [...refreshRunQueryKey, requestedAt?.toISOString() ?? null],
    queryFn: () => (requestedAt === null ? Promise.resolve(null) : fetchRunSince(requestedAt)),
    enabled: requestedAt !== null,
    staleTime: 0,
    refetchInterval: (query) => {
      if (requestedAt === null) return false;
      const progress = refreshProgress(query.state.data ?? null, requestedAt, clock.now());
      return nextCheckDelay(query.state.dataUpdateCount, progress.kind);
    },
  });

  useEffect(() => {
    if (requestedAt === null) return;
    // Polling stops by itself at the limit, and a run that never shows up
    // changes nothing on screen. Re-render once the limit has passed so the
    // "timed out" state is reached and the button is freed.
    const timeLeft = watchTimeLeftMs(requestedAt, clock.now());
    if (timeLeft === 0) return;
    const timer = setTimeout(() => {
      setWatchChecks((checks) => checks + 1);
    }, timeLeft);
    return () => {
      clearTimeout(timer);
    };
  }, [requestedAt, clock]);

  if (requestedAt === null) return null;
  return { run: watch.data ?? null, progress: refreshProgress(watch.data ?? null, requestedAt, clock.now()) };
}

/**
 * The "Refresh now" button's state: asks the refresh service for an extra run,
 * then follows that run in the run history until it finishes.
 */
export function useRefreshNow(): RefreshNow {
  const queryClient = useQueryClient();
  const mutation = useMutation({ mutationFn: requestRefresh });
  const outcome = mutation.data;
  const watched = useRefreshWatch(outcome?.kind === 'started' ? outcome : null);
  const finishedRunId = watched?.progress.kind === 'finished' ? watched.run?.id : undefined;
  const finishedWell =
    watched?.progress.kind === 'finished' && watched.progress.runStatus === 'success';
  const { reset } = mutation;

  useEffect(() => {
    if (finishedRunId === undefined) return;
    // New messages have arrived: reload everything except the watch itself.
    void queryClient.invalidateQueries({
      predicate: (query) => query.queryKey[0] !== refreshRunQueryKey[0],
    });
  }, [finishedRunId, queryClient]);

  useEffect(() => {
    if (!finishedWell) return;
    // Nothing more to say once it worked: the line clears itself after a moment.
    const timer = setTimeout(reset, REFRESH_DONE_SHOWN_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [finishedWell, reset]);

  return {
    status: currentStatus(mutation, outcome, watched?.progress ?? null),
    start: () => {
      mutation.mutate();
    },
  };
}

function currentStatus(
  mutation: { isPending: boolean; isError: boolean },
  outcome: RefreshOutcome | undefined,
  progress: RefreshStatus | null,
): RefreshStatus {
  if (mutation.isPending) return { kind: 'sending' };
  if (mutation.isError) {
    return { kind: 'refused', code: 'unexpected', target: null, retryAfterMinutes: null };
  }
  if (outcome?.kind === 'refused') return refusalStatus(outcome);
  if (progress !== null) return progress;
  return { kind: 'idle' };
}
