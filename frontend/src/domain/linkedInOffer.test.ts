import { describe, expect, it } from 'vitest';
import type { RunStatus, RunStep } from '../types/database';
import { linkedInMissing } from './linkedInOffer';

function run(startedAt: string, status: RunStatus, steps: RunStep[]) {
  return { started_at: startedAt, status, run_step_logs: steps.map((step) => ({ step })) };
}

describe('linkedInMissing', () => {
  it('knows nothing, and offers nothing, before a run has read a source', () => {
    expect(linkedInMissing([])).toBe(false);
    expect(linkedInMissing([run('2026-10-10T05:00:00Z', 'failed', [])])).toBe(false);
  });

  it('is true when the newest run read the mailbox but not LinkedIn', () => {
    expect(linkedInMissing([run('2026-10-10T05:00:00Z', 'success', ['collect_email', 'assess'])])).toBe(
      true,
    );
  });

  it('is false when the newest run read LinkedIn, even if it failed there', () => {
    expect(
      linkedInMissing([run('2026-10-10T05:00:00Z', 'partial', ['collect_linkedin', 'collect_email'])]),
    ).toBe(false);
  });

  it('goes by the newest finished run, whatever the order it is given in', () => {
    const older = run('2026-10-09T05:00:00Z', 'success', ['collect_email']);
    const newer = run('2026-10-10T05:00:00Z', 'success', ['collect_linkedin', 'collect_email']);
    expect(linkedInMissing([older, newer])).toBe(false);
    expect(linkedInMissing([newer, older])).toBe(false);
  });

  it('leaves out a run still going and one that stopped before reading anything', () => {
    const connected = run('2026-10-09T05:00:00Z', 'success', ['collect_linkedin', 'collect_email']);
    const going = run('2026-10-10T05:00:00Z', 'running', ['collect_email']);
    const stoppedEarly = run('2026-10-10T06:00:00Z', 'failed', []);
    expect(linkedInMissing([connected, going, stoppedEarly])).toBe(false);
  });
});
