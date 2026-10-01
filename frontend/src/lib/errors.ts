/** The errors the dashboard raises. Nothing else is thrown on purpose. */

/** Base class so a single `instanceof` catches anything we raised ourselves. */
export class DashboardError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

/** The two `VITE_` settings are missing, so there is nothing to talk to. */
export class NotConfiguredError extends DashboardError {}

/** The database refused or could not be reached. */
export class DataUnavailableError extends DashboardError {}

/** The database answered, but not in the shape the dashboard expects. */
export class UnexpectedDataError extends DashboardError {}

/** The session is gone or was never valid. */
export class NotSignedInError extends DashboardError {}

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

  constructor(reason: RefusalReason, message: string, options?: ErrorOptions) {
    super(message, options);
    this.reason = reason;
  }
}
