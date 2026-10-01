import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { NOW } from '../test/__fixtures__/sampleData';
import { fixedClock } from './clock';
import {
  describeStepCounts,
  explainRunError,
  explainRunTrigger,
  formatClockTime,
  formatDate,
  formatDuration,
  formatRelative,
  formatRoleLine,
  formatWeekday,
} from './format';

const clock = fixedClock(NOW);

describe('formatDate', () => {
  it('writes a date the way a person reads it', () => {
    expect(formatDate('2026-03-14')).toBe('14 Mar 2026');
  });

  it('says "not set" rather than showing nothing', () => {
    expect(formatDate(null)).toBe(copy.values.none);
  });

  it('does not print rubbish for a broken value', () => {
    expect(formatDate('not-a-date')).toBe(copy.values.none);
  });
});

describe('formatWeekday and formatClockTime', () => {
  // Built from local parts, so the test holds in whatever time zone it runs.
  const localMeeting = new Date(2026, 2, 13, 14, 30).toISOString();

  it('writes the day of a meeting in local time', () => {
    expect(formatWeekday(localMeeting)).toBe('Fri 13 Mar');
  });

  it('writes the time of a meeting in local time', () => {
    expect(formatClockTime(localMeeting)).toBe('14:30');
  });

  it('does not print rubbish for a broken value', () => {
    expect(formatWeekday('not-a-date')).toBe(copy.values.none);
    expect(formatClockTime('not-a-date')).toBe(copy.values.none);
  });
});

describe('formatRelative', () => {
  it('counts in hours for something from this morning', () => {
    expect(formatRelative('2026-03-12T06:00:00.000Z', clock)).toBe(copy.time.hoursAgo(3));
  });

  it('says "yesterday" for the day before', () => {
    expect(formatRelative('2026-03-11T08:00:00.000Z', clock)).toBe(copy.time.daysAgo(1));
  });

  it('falls back to a plain date once it is more than a week old', () => {
    expect(formatRelative('2026-02-18T11:00:00.000Z', clock)).toBe('18 Feb 2026');
  });

  it('says "never" when there is no date at all', () => {
    expect(formatRelative(null, clock)).toBe(copy.values.never);
  });
});

describe('formatDuration', () => {
  it('reads as minutes and seconds', () => {
    expect(formatDuration('2026-03-12T05:00:00.000Z', '2026-03-12T05:02:10.000Z')).toBe('2m 10s');
  });

  it('says a run is still going when it has not finished', () => {
    expect(formatDuration('2026-03-12T05:00:00.000Z', null)).toBe(copy.runs.stillRunning);
  });
});

describe('explainRunError', () => {
  it('turns a known code into a sentence', () => {
    expect(explainRunError('source_auth_failed')).toBe(copy.runErrors.source_auth_failed);
  });

  it('says plainly that a run was interrupted', () => {
    const explanation = explainRunError('run_interrupted');
    expect(explanation).toBe(copy.runErrors.run_interrupted);
    expect(explanation).toContain('never finished');
  });

  it('never shows an unknown code to the user', () => {
    const explanation = explainRunError('some_new_code');
    expect(explanation).toBe(copy.runErrorFallback);
    expect(explanation).not.toContain('some_new_code');
  });

  it('says nothing when the step had no problem', () => {
    expect(explainRunError(null)).toBeNull();
    expect(explainRunError('  ')).toBeNull();
  });
});

describe('explainRunTrigger', () => {
  it('names what set the run going in plain words', () => {
    expect(explainRunTrigger('cloud')).toBe(copy.runTriggerLabels.cloud);
    expect(explainRunTrigger('manual')).toBe(copy.runTriggerLabels.manual);
  });

  it('never names the service behind the schedule', () => {
    for (const trigger of ['cloud', 'github']) {
      expect(explainRunTrigger(trigger)).toBe('the daily schedule');
    }
  });

  it('does not echo a value it does not recognise', () => {
    expect(explainRunTrigger('some_future_thing')).toBe(copy.runTriggerFallback);
  });
});

describe('formatRoleLine', () => {
  it.each([
    ['Founder', 'Acme', 'Founder · Acme'],
    ['Founder', null, 'Founder'],
    [null, 'Acme', 'Acme'],
    [null, null, null],
    ['', null, null],
  ])('joins %j and %j as %j', (role, organisation, expected) => {
    expect(formatRoleLine(role, organisation)).toBe(expected);
  });
});

describe('describeStepCounts', () => {
  it('shows what a reading step found and how much was new', () => {
    expect(describeStepCounts({ step: 'collect_email', items_found: 12, items_new: 3 })).toEqual([
      '12 found',
      '3 new',
    ]);
    expect(describeStepCounts({ step: 'assess', items_found: null, items_new: null })).toEqual([]);
  });

  it('says the morning e-mail was sent rather than "1 found, 1 new"', () => {
    expect(describeStepCounts({ step: 'summary_email', items_found: 1, items_new: 1 })).toEqual([
      copy.runs.emailSent,
    ]);
    expect(describeStepCounts({ step: 'summary_email', items_found: 0, items_new: 0 })).toEqual(
      [],
    );
  });
});
