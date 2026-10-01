import { describe, expect, it } from 'vitest';
import { fixedClock } from '../lib/clock';
import type { RunLogRow, RunStatus } from '../types/database';
import { assessRunHealth } from './runHealth';

const NOW = new Date('2026-03-12T09:00:00.000Z');
const clock = fixedClock(NOW);

/** Builds a run that finished `hoursAgo` before the frozen "now". */
function run(id: string, status: RunStatus, hoursAgo: number): RunLogRow {
  const finished = new Date(NOW.getTime() - hoursAgo * 3_600_000);
  const started = new Date(finished.getTime() - 120_000);
  return {
    id,
    created_at: started.toISOString(),
    updated_at: finished.toISOString(),
    started_at: started.toISOString(),
    finished_at: finished.toISOString(),
    status,
    trigger: 'cloud',
  };
}

describe('assessRunHealth', () => {
  it('reports "never" when there has been no run at all', () => {
    expect(assessRunHealth([], clock)).toEqual({ kind: 'never' });
  });

  it('is happy with a successful run from this morning', () => {
    const health = assessRunHealth([run('a', 'success', 4)], clock);
    expect(health.kind).toBe('ok');
  });

  it('accepts a run that is 26 hours old exactly', () => {
    expect(assessRunHealth([run('a', 'success', 26)], clock).kind).toBe('ok');
  });

  it('calls the list stale once the last good run passes 26 hours', () => {
    expect(assessRunHealth([run('a', 'success', 26.5)], clock).kind).toBe('stale');
  });

  it('still warns at 27 hours, the day after a missed run', () => {
    const health = assessRunHealth([run('a', 'success', 27)], clock);
    expect(health).toEqual({
      kind: 'stale',
      lastSuccessAt: new Date(NOW.getTime() - 27 * 3_600_000),
    });
  });

  it('warns when the newest finished run failed, however recent it was', () => {
    const health = assessRunHealth([run('new', 'failed', 1), run('old', 'success', 25)], clock);
    expect(health.kind).toBe('failed');
  });

  it('ignores a run that is still going and judges the one before it', () => {
    const runs = [run('now', 'running', 0), run('yesterday', 'success', 3)];
    expect(assessRunHealth(runs, clock).kind).toBe('ok');
  });

  it('treats a partly successful run as good enough to be up to date', () => {
    expect(assessRunHealth([run('a', 'partial', 2)], clock).kind).toBe('ok');
  });

  it('does not depend on the order the runs arrive in', () => {
    const runs = [run('old', 'success', 30), run('new', 'success', 2)];
    expect(assessRunHealth(runs, clock).kind).toBe('ok');
    expect(assessRunHealth([...runs].reverse(), clock).kind).toBe('ok');
  });

  it('moves from happy to stale as the injected clock advances', () => {
    const runs = [run('a', 'success', 1)];
    expect(assessRunHealth(runs, clock).kind).toBe('ok');

    const laterClock = fixedClock(new Date(NOW.getTime() + 26 * 3_600_000));
    expect(assessRunHealth(runs, laterClock).kind).toBe('stale');
  });
});
