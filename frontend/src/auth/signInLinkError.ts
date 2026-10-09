import * as copy from '../copy/en';
import { SignInLinkError, SignInRefusal } from '../lib/errors';

/** The parts of a Supabase `AuthError` the sign-in page reads. */
export interface AuthFailure {
  code?: string | undefined;
  status?: number | undefined;
  message: string;
}

/**
 * Codes that mean "this address will never get a link from this page".
 *
 * - `otp_disabled`: the page asks with `shouldCreateUser: false` and no login
 *   has this address ("Signups not allowed for otp", HTTP 422).
 * - `signup_disabled`: the same refusal when a new login would be needed and
 *   sign-ups are switched off for the project.
 * - `email_address_not_authorized`: Supabase's own free e-mail only reaches the
 *   members of the Supabase account.
 */
const UNKNOWN_ADDRESS_CODES: ReadonlySet<string> = new Set([
  'otp_disabled',
  'signup_disabled',
  'email_address_not_authorized',
]);

/** Codes for "too many links asked for"; Supabase answers both with HTTP 429. */
const TOO_MANY_REQUESTS_CODES: ReadonlySet<string> = new Set([
  'over_email_send_rate_limit',
  'over_request_rate_limit',
]);

const TOO_MANY_REQUESTS_STATUS = 429;

/**
 * Supabase's short per-address wait says how long it lasts, as in "For security
 * purposes, you can only request this after 52 seconds." The text is not a
 * promise, so a message without it simply leaves the wait unknown.
 */
const WAIT_SECONDS_PATTERN = /after (\d+) seconds?/i;

function waitSecondsFrom(message: string): number | null {
  const match = WAIT_SECONDS_PATTERN.exec(message);
  return match?.[1] === undefined ? null : Number(match[1]);
}

/** Turns Supabase's refusal into the reason the owner can act on. */
export function toSignInLinkError(failure: AuthFailure): SignInLinkError {
  const code = failure.code ?? '';
  if (UNKNOWN_ADDRESS_CODES.has(code)) {
    return new SignInLinkError(SignInRefusal.UnknownAddress);
  }
  if (TOO_MANY_REQUESTS_CODES.has(code) || failure.status === TOO_MANY_REQUESTS_STATUS) {
    return new SignInLinkError(SignInRefusal.TooManyRequests, waitSecondsFrom(failure.message));
  }
  return new SignInLinkError(SignInRefusal.Unavailable);
}

/**
 * What the sign-in page says when no link was sent. Only a refusal with a
 * known cause gets its own advice; anything else is worth simply trying again.
 */
export function signInFailureMessage(error: unknown): string {
  if (!(error instanceof SignInLinkError)) return copy.login.failed;
  switch (error.reason) {
    case SignInRefusal.UnknownAddress:
      return copy.login.unknownAddress;
    case SignInRefusal.TooManyRequests:
      return copy.login.tooManyLinks(error.retryAfterSeconds);
    case SignInRefusal.Unavailable:
      return copy.login.failed;
  }
}
