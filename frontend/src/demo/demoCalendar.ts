/** Date helpers for the demo, so every invented date sits around "today". */

/** A moment `dayOffset` days from `now`, at a set local time of day. */
export function atLocal(now: Date, dayOffset: number, hour: number, minute = 0): string {
  const moment = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + dayOffset,
    hour,
    minute,
  );
  return moment.toISOString();
}

/** `dayOffset` days from `now` as a plain local date (`YYYY-MM-DD`), like a due date. */
export function localDate(now: Date, dayOffset = 0): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + dayOffset);
  const month = String(day.getMonth() + 1).padStart(2, '0');
  const date = String(day.getDate()).padStart(2, '0');
  return `${day.getFullYear()}-${month}-${date}`;
}

const HOUR_MS = 3_600_000;

/** A moment `hours` before `now`. */
export function hoursBefore(now: Date, hours: number): string {
  return new Date(now.getTime() - hours * HOUR_MS).toISOString();
}

/** The daily job starts at this local hour and is done a few minutes later. */
const DAILY_RUN_HOUR = 5;
const RUN_MINUTES = 3;
const MINUTE_MS = 60_000;

/**
 * When the daily job started `daysBack` days before the latest run. Before
 * the run hour, the latest run is yesterday's.
 */
export function dailyRunStart(now: Date, daysBack = 0): string {
  const latest = now.getHours() > DAILY_RUN_HOUR ? 0 : -1;
  return atLocal(now, latest - daysBack, DAILY_RUN_HOUR);
}

/** When a daily run that started at `startedAt` finished. */
export function dailyRunEnd(startedAt: string): string {
  return new Date(new Date(startedAt).getTime() + RUN_MINUTES * MINUTE_MS).toISOString();
}
