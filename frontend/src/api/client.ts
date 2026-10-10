import type { z } from 'zod';
import {
  DataUnavailableError,
  NotAllowedError,
  NotSignedInError,
  RefusalReason,
  RefusedError,
  TableMissingError,
  UnexpectedDataError,
} from '../lib/errors';
import { logError, logInfo } from '../lib/logger';

/**
 * The one place a Supabase response is turned into typed data.
 *
 * Every read goes through here, so validation, error mapping and logging happen
 * exactly once instead of in every module.
 */

/** The part of a Supabase response this layer cares about. */
export interface SupabaseResult {
  data: unknown;
  error: { message: string; code?: string } | null;
  status?: number;
}

const UNAUTHORISED_STATUS = 401;
const FORBIDDEN_STATUS = 403;
const EXPIRED_TOKEN_CODE = 'PGRST301';

/** Postgres error codes for a write refused on purpose, and what each means. */
const REFUSAL_CODES = new Map<string, RefusalReason>([
  ['23503', RefusalReason.InUse],
  ['23514', RefusalReason.BreaksRule],
  ['23505', RefusalReason.Duplicate],
]);

/**
 * Postgres's and the data API's codes for a table (`42P01`, `PGRST205`) or a
 * column (`42703`) the database does not have (yet).
 */
const MISSING_TABLE_CODES = new Set(['42P01', 'PGRST205', '42703']);

/** Where Postgres names the rule a refused write broke: `… constraint "name"`. */
const CONSTRAINT_NAME = /constraint "([^"]+)"/;

/** The rule a refusal names, or null when its message names none. */
function constraintName(message: string): string | null {
  return CONSTRAINT_NAME.exec(message)?.[1] ?? null;
}

/** How a caller wants a write handled. */
export interface MutationOptions {
  /**
   * Refusals the caller handles as a normal outcome (for example, hiding a
   * category the database will not delete). They are logged as information,
   * not as errors, and still raised so the caller can act on them.
   */
  expectedRefusals?: readonly RefusalReason[];
}

function toDomainError(
  event: string,
  result: SupabaseResult,
  { expectedRefusals = [] }: MutationOptions = {},
): Error {
  const { error, status } = result;
  const code = error?.code ?? null;

  if (status === UNAUTHORISED_STATUS || code === EXPIRED_TOKEN_CODE) {
    logError('query.not_signed_in', { event, code, status: status ?? null });
    return new NotSignedInError(event);
  }

  if (status === FORBIDDEN_STATUS) {
    logError('query.not_allowed', { event, code, status: status ?? null });
    return new NotAllowedError(event);
  }

  if (code !== null && MISSING_TABLE_CODES.has(code)) {
    logError('query.table_missing', { event, code, status: status ?? null });
    return new TableMissingError(event);
  }

  const reason = code === null ? undefined : REFUSAL_CODES.get(code);
  if (reason !== undefined) {
    const fields = { event, code, status: status ?? null };
    if (expectedRefusals.includes(reason)) logInfo('query.refused_as_expected', fields);
    else logError('query.refused', fields);
    return new RefusedError(reason, event, constraintName(error?.message ?? ''));
  }

  logError('query.failed', { event, code, status: status ?? null });
  return new DataUnavailableError(event);
}

/**
 * Runs a Supabase query and validates what came back.
 *
 * @param event Short identifier used in logs — never contains personal data.
 * @param schema Runtime shape the answer must match.
 * @param execute The Supabase query builder call.
 * @throws {NotSignedInError} when the session is missing or expired.
 * @throws {NotAllowedError} when the account is signed in but not allowed.
 * @throws {DataUnavailableError} when the database refused or was unreachable.
 * @throws {UnexpectedDataError} when the answer did not match the schema.
 */
export async function runQuery<T>(
  event: string,
  schema: z.ZodType<T>,
  execute: () => PromiseLike<SupabaseResult>,
): Promise<T> {
  let result: SupabaseResult;
  try {
    result = await execute();
  } catch (cause) {
    logError('query.threw', { event });
    throw new DataUnavailableError(event, { cause });
  }

  if (result.error !== null) throw toDomainError(event, result);

  const parsed = schema.safeParse(result.data);
  if (!parsed.success) {
    logError('query.unexpected_shape', { event, issues: parsed.error.issues.length });
    throw new UnexpectedDataError(event);
  }
  return parsed.data;
}

/**
 * Runs a Supabase write that returns nothing worth reading.
 *
 * @param event Short identifier used in logs — never contains personal data.
 * @param execute The Supabase query builder call.
 * @param options Which refusals are an expected outcome rather than an error.
 * @throws {NotSignedInError} when the session is missing or expired.
 * @throws {NotAllowedError} when the account is signed in but not allowed.
 * @throws {RefusedError} when the database refused it on purpose (a rule, a
 *   duplicate, or a row something still points at).
 * @throws {DataUnavailableError} when the write failed for any other reason.
 */
export async function runMutation(
  event: string,
  execute: () => PromiseLike<SupabaseResult>,
  options: MutationOptions = {},
): Promise<void> {
  let result: SupabaseResult;
  try {
    result = await execute();
  } catch (cause) {
    logError('mutation.threw', { event });
    throw new DataUnavailableError(event, { cause });
  }

  if (result.error !== null) throw toDomainError(event, result, options);
}
