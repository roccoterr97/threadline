import { describe, expect, it } from 'vitest';
import {
  REFRESH_FIRST_CHECK_MS,
  REFRESH_POLL_INTERVAL_MS,
  REFRESH_RUN_MATCH_SLACK_MS,
} from '../constants/dashboard';
import type { RunLogRow, RunStatus } from '../types/database';
import { nextCheckDelay, refreshIsBusy, refreshProgress, refusalStatus, watchStart, watchTimeLeftMs } from './refresh';

const REQUESTED = new Date('2026-09-29T10:00:00Z');

function minutesLater(minutes: number): Date {
  return new Date(REQUESTED.getTime() + minutes * 60_000);
}

function run(status: RunStatus): RunLogRow {
  const stamp = REQUESTED.toISOString();
  return {
    id: 'run-1',
    created_at: stamp,
    updated_at: stamp,
    started_at: stamp,
    finished_at: status === 'running' ? null : stamp,
    status,
    trigger: 'refresh',
  };
}

describe('refreshProgress', () => {
  it('waits while no run has shown up yet', () => {
    expect(refreshProgress(null, REQUESTED, minutesLater(2))).toEqual({ kind: 'waiting' });
  });

  it('waits while the run is going', () => {
    expect(refreshProgress(run('running'), REQUESTED, minutesLater(5))).toEqual({ kind: 'waiting' });
  });

  it.each<RunStatus>(['success', 'partial', 'failed'])('reports a %s run as finished', (status) => {
    expect(refreshProgress(run(status), REQUESTED, minutesLater(5))).toEqual({
      kind: 'finished',
      runStatus: status,
    });
  });

  it('gives up watching after fifteen minutes', () => {
    expect(refreshProgress(run('running'), REQUESTED, minutesLater(15))).toEqual({
      kind: 'timed_out',
    });
  });

  it('still reports a finish that arrives after the watch limit', () => {
    expect(refreshProgress(run('success'), REQUESTED, minutesLater(20)).kind).toBe('finished');
  });
});

describe('watchTimeLeftMs', () => {
  it('counts down from fifteen minutes and stops at zero', () => {
    expect(watchTimeLeftMs(REQUESTED, REQUESTED)).toBe(15 * 60_000);
    expect(watchTimeLeftMs(REQUESTED, minutesLater(10))).toBe(5 * 60_000);
    expect(watchTimeLeftMs(REQUESTED, minutesLater(15))).toBe(0);
    expect(watchTimeLeftMs(REQUESTED, minutesLater(40))).toBe(0);
  });
});

describe('nextCheckDelay', () => {
  it('looks again soon the first time, then every half minute, then stops', () => {
    expect(nextCheckDelay(1, 'waiting')).toBe(REFRESH_FIRST_CHECK_MS);
    expect(nextCheckDelay(2, 'waiting')).toBe(REFRESH_POLL_INTERVAL_MS);
    expect(nextCheckDelay(3, 'finished')).toBe(false);
    expect(nextCheckDelay(3, 'timed_out')).toBe(false);
  });
});

describe('watchStart', () => {
  it('allows for a small clock difference', () => {
    expect(REQUESTED.getTime() - watchStart(REQUESTED).getTime()).toBe(REFRESH_RUN_MATCH_SLACK_MS);
  });
});

describe('refusalStatus', () => {
  it('rounds the wait up to whole minutes, never below one', () => {
    const base = { kind: 'refused', code: 'too_soon', target: 'github' } as const;
    expect(refusalStatus({ ...base, retryAfterSeconds: 61 }).retryAfterMinutes).toBe(2);
    expect(refusalStatus({ ...base, retryAfterSeconds: 5 }).retryAfterMinutes).toBe(1);
    expect(refusalStatus({ ...base, retryAfterSeconds: null }).retryAfterMinutes).toBeNull();
  });
});

describe('refreshIsBusy', () => {
  it('is busy only while asking and while waiting', () => {
    expect(refreshIsBusy({ kind: 'sending' })).toBe(true);
    expect(refreshIsBusy({ kind: 'waiting' })).toBe(true);
    expect(refreshIsBusy({ kind: 'idle' })).toBe(false);
    expect(refreshIsBusy({ kind: 'timed_out' })).toBe(false);
  });
});
