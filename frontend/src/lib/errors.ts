/** The errors the dashboard raises. Nothing else is thrown on purpose. */

/** Base class so a single `instanceof` catches anything we raised ourselves. */
export class DashboardError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

/** The page has no database address and key, so there is nothing to talk to. */
export class NotConfiguredError extends DashboardError {}

/** The database refused or could not be reached. */
export class DataUnavailableError extends DashboardError {}

/**
 * The database has no such table or column: a structure file newer than the
 * database has not been applied yet. A kind of "unavailable" a page can explain.
 */
export class TableMissingError extends DataUnavailableError {}

/** The database answered, but not in the shape the dashboard expects. */
export class UnexpectedDataError extends DashboardError {}

/** The session is gone or was never valid. */
export class NotSignedInError extends DashboardError {}

/**
 * The session is fine but the database refuses this account (a 403): it is
 * signed in as someone other than the owner. Signing in again will not help.
 */
export class NotAllowedError extends DashboardError {}

/** Why the database turned a write down on purpose, as opposed to failing. */
export enum RefusalReason {
  /** Something still points at the row (Postgres 23503, a foreign key). */
  InUse = 'in_use',
  /** The change breaks one of the table's rules (Postgres 23514, a check). */
  BreaksRule = 'breaks_rule',
  /** Another row already has that value (Postgres 23505, a unique key). */
  Duplicate = 'duplicate',
}

/** The database understood the write and refused it for a known reason. */
export class RefusedError extends DashboardError {
  readonly reason: RefusalReason;
  /** The database rule that refused the write, when the database named one. */
  readonly constraint: string | null;

  constructor(
    reason: RefusalReason,
    message: string,
    constraint: string | null = null,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.reason = reason;
    this.constraint = constraint;
  }
}

/** Why Supabase would not send a sign-in link, as far as the owner can act on it. */
export enum SignInRefusal {
  /** No dashboard login uses this address, and sign-ups are off. */
  UnknownAddress = 'unknown_address',
  /** Too many links were asked for in a short time. */
  TooManyRequests = 'too_many_requests',
  /** Anything else: no connection, a server fault, an unknown code. */
  Unavailable = 'unavailable',
}

/** Supabase did not send the sign-in link. */
export class SignInLinkError extends DashboardError {
  readonly reason: SignInRefusal;
  /** How long Supabase asked to wait, when it said; otherwise null. */
  readonly retryAfterSeconds: number | null;

  constructor(
    reason: SignInRefusal,
    retryAfterSeconds: number | null = null,
    options?: ErrorOptions,
  ) {
    super(`sign-in link not sent: ${reason}`, options);
    this.reason = reason;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}
