import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { sampleStatusLabels } from '../test/__fixtures__/sampleData';
import { resolveStatusLabels } from './vocabulary';

describe('resolveStatusLabels', () => {
  it('uses the owner\'s own name for every status that has a row', () => {
    const labels = resolveStatusLabels(sampleStatusLabels, copy.defaultStatusLabels);
    expect(labels.in_process).toBe('In a hiring process');
    expect(labels.closed).toBe('Closed');
  });

  it('falls back to the neutral name for a status with no row', () => {
    const withoutInProcess = sampleStatusLabels.filter((row) => row.status !== 'in_process');
    const labels = resolveStatusLabels(withoutInProcess, copy.defaultStatusLabels);
    expect(labels.in_process).toBe('In process');
    expect(labels.meeting_planned).toBe('Meeting planned');
  });

  it('falls back to every neutral name when nothing was loaded', () => {
    expect(resolveStatusLabels(undefined, copy.defaultStatusLabels)).toEqual(
      copy.defaultStatusLabels,
    );
  });
});
