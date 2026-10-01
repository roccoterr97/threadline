/** Operational tuning for the dashboard. No deployment settings live here. */

/**
 * A successful run older than this counts as stale and raises the banner.
 * 26 hours, not 24, so a run that starts a little late does not cry wolf.
 */
export const STALE_RUN_HOURS = 26;

/** How many past runs `/runs` shows. */
export const RUN_HISTORY_LIMIT = 14;

/** How long fetched data is treated as fresh before TanStack Query refetches. */
export const QUERY_STALE_TIME_MS = 60_000;

/** Failed reads are retried this many times before the error state shows. */
export const QUERY_RETRY_ATTEMPTS = 2;

/** Upper bound on the people list, so one query can never grow unbounded. */
export const PEOPLE_PAGE_SIZE = 500;

/** Upper bound on the messages shown in one person's timeline. */
export const TIMELINE_MESSAGE_LIMIT = 500;

/** Upper bound on the open questions fetched for the review list. */
export const REVIEW_PAGE_SIZE = 200;

/** A timeline message longer than this many lines is folded to its first lines. */
export const MESSAGE_FOLD_LINES = 6;

/** A timeline message longer than this many characters is folded to its opening. */
export const MESSAGE_FOLD_CHARACTERS = 400;

/** How many days ahead the "Coming up" strip looks for meetings. */
export const COMING_UP_DAYS = 7;

/** Upper bound on the meetings the "Coming up" strip fetches. */
export const COMING_UP_LIMIT = 20;

/**
 * How long the categories and status labels count as fresh. The owner changes
 * them at most once a day, from a file, so an hour is plenty.
 */
export const VOCABULARY_STALE_TIME_MS = 60 * 60 * 1000;

/** Upper bound on the categories fetched; a profile has a handful. */
export const CATEGORIES_LIMIT = 100;

/** How often a started "Refresh now" run is checked on while it goes. */
export const REFRESH_POLL_INTERVAL_MS = 30_000;

/** The first check on a started refresh comes sooner, in case the run is quick. */
export const REFRESH_FIRST_CHECK_MS = 5_000;

/** After this long the dashboard stops watching a refresh and points to the run history. */
export const REFRESH_WATCH_LIMIT_MINUTES = 15;

/** A run that started this long before the refresh was asked for still counts as its run. */
export const REFRESH_RUN_MATCH_SLACK_MS = 60_000;

/**
 * How long "Refresh finished" stays under the header once everything worked.
 * A refresh that went wrong keeps its message until the next one starts.
 */
export const REFRESH_DONE_SHOWN_MS = 10_000;

/** How long the demo's pretend refresh takes before it finishes. */
export const DEMO_REFRESH_SECONDS = 4;
