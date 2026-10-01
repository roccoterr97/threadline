import * as copy from '../copy/en';
import type { RunStepLogRow } from '../types/database';
import type { Clock } from './clock';

const LOCALE = 'en-GB';

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const weekdayFormatter = new Intl.DateTimeFormat(LOCALE, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
});

const clockTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
});

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

/** "12 Mar 2026", or the "not set" wording for a missing value. */
export function formatDate(value: string | null): string {
  if (value === null) return copy.values.none;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return copy.values.none;
  return dateFormatter.format(date);
}

/** "12 Mar 2026, 09:14". */
export function formatDateTime(value: string | null): string {
  if (value === null) return copy.values.none;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return copy.values.none;
  return dateTimeFormatter.format(date);
}

/** "Fri 13 Mar" in the browser's own time zone, or "not set" for a broken value. */
export function formatWeekday(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return copy.values.none;
  return weekdayFormatter.format(date);
}

/** "14:30" in the browser's own time zone, or "not set" for a broken value. */
export function formatClockTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return copy.values.none;
  return clockTimeFormatter.format(date);
}

/** "3 hours ago" for anything recent, an absolute date once it is older. */
export function formatRelative(value: string | Date | null, clock: Clock): string {
  if (value === null) return copy.values.never;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return copy.values.never;

  const elapsed = clock.now().getTime() - date.getTime();
  if (elapsed < MINUTE_MS) return copy.time.justNow;
  if (elapsed < HOUR_MS) return copy.time.minutesAgo(Math.floor(elapsed / MINUTE_MS));
  if (elapsed < DAY_MS) return copy.time.hoursAgo(Math.floor(elapsed / HOUR_MS));
  if (elapsed < 7 * DAY_MS) return copy.time.daysAgo(Math.floor(elapsed / DAY_MS));
  return dateFormatter.format(date);
}

/** "4 min 12 s" between two timestamps, or the "still running" wording. */
export function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (finishedAt === null) return copy.runs.stillRunning;
  const elapsed = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (Number.isNaN(elapsed) || elapsed < 0) return copy.values.unknown;
  const totalSeconds = Math.round(elapsed / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes === 0 ? `${seconds}s` : `${minutes}m ${seconds}s`;
}

/**
 * "Role · Organisation" with whatever is known, or null when neither is.
 * A missing part is left out rather than shown as "Not known", which the
 * category chip next to it may already say.
 */
export function formatRoleLine(role: string | null, organisation: string | null): string | null {
  const parts = [role, organisation].filter((part): part is string => part !== null && part !== '');
  return parts.length === 0 ? null : parts.join(' · ');
}

/**
 * The short counts shown after a run step, such as "12 found" and "3 new".
 * The morning e-mail step stores a count of one for the one e-mail it sent,
 * which reads as nonsense ("1 found, 1 new"), so it just says "sent".
 */
export function describeStepCounts(
  step: Pick<RunStepLogRow, 'step' | 'items_found' | 'items_new'>,
): string[] {
  if (step.step === 'summary_email') {
    const sent = (step.items_new ?? 0) > 0 || (step.items_found ?? 0) > 0;
    return sent ? [copy.runs.emailSent] : [];
  }
  const counts: string[] = [];
  if (step.items_found !== null) counts.push(`${step.items_found} ${copy.runs.found}`);
  if (step.items_new !== null) counts.push(`${step.items_new} ${copy.runs.new}`);
  return counts;
}

/** Turns a stored error code into something the owner can act on. */
export function explainRunError(errorCode: string | null): string | null {
  if (errorCode === null || errorCode.trim() === '') return null;
  return copy.runErrors[errorCode] ?? copy.runErrorFallback;
}

/** Turns a stored trigger value into words rather than a system name. */
export function explainRunTrigger(trigger: string): string {
  return copy.runTriggerLabels[trigger] ?? copy.runTriggerFallback;
}
