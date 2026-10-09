import { AuthApiError, AuthRetryableFetchError } from '@supabase/supabase-js';
import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { SignInLinkError, SignInRefusal } from '../lib/errors';
import { signInFailureMessage, toSignInLinkError } from './signInLinkError';

describe('toSignInLinkError', () => {
  it.each([
    ['otp_disabled', 'Signups not allowed for otp'],
    ['signup_disabled', 'Signups not allowed for this instance'],
    ['email_address_not_authorized', 'Email address not authorized'],
  ])('reads %s as an address that cannot sign in', (code, message) => {
    const error = toSignInLinkError(new AuthApiError(message, 422, code));
    expect(error.reason).toBe(SignInRefusal.UnknownAddress);
  });

  it('takes the wait from the short per-address limit', () => {
    const error = toSignInLinkError(
      new AuthApiError(
        'For security purposes, you can only request this after 52 seconds.',
        429,
        'over_email_send_rate_limit',
      ),
    );
    expect(error.reason).toBe(SignInRefusal.TooManyRequests);
    expect(error.retryAfterSeconds).toBe(52);
  });

  it('leaves the wait unknown when Supabase does not give one', () => {
    const error = toSignInLinkError(
      new AuthApiError('email rate limit exceeded', 429, 'over_email_send_rate_limit'),
    );
    expect(error.reason).toBe(SignInRefusal.TooManyRequests);
    expect(error.retryAfterSeconds).toBeNull();
  });

  it('counts any 429 as too many requests, even under an unknown code', () => {
    const error = toSignInLinkError(new AuthApiError('Request rate limit reached', 429, 'something_new'));
    expect(error.reason).toBe(SignInRefusal.TooManyRequests);
  });

  it('reads a lost connection as unavailable', () => {
    const error = toSignInLinkError(new AuthRetryableFetchError('Failed to fetch', 0));
    expect(error.reason).toBe(SignInRefusal.Unavailable);
  });

  it('reads a server fault as unavailable', () => {
    const error = toSignInLinkError(new AuthRetryableFetchError('Bad Gateway', 502));
    expect(error.reason).toBe(SignInRefusal.Unavailable);
  });
});

describe('signInFailureMessage', () => {
  it('names the rule for an address that cannot sign in', () => {
    const error = new SignInLinkError(SignInRefusal.UnknownAddress);
    expect(signInFailureMessage(error)).toBe(copy.login.unknownAddress);
  });

  it('says how long to wait when it is known', () => {
    const error = new SignInLinkError(SignInRefusal.TooManyRequests, 52);
    expect(signInFailureMessage(error)).toBe(
      'Too many links were asked for. Please wait 52 seconds, then try again.',
    );
  });

  it('says up to an hour when the wait is not known', () => {
    const error = new SignInLinkError(SignInRefusal.TooManyRequests);
    expect(signInFailureMessage(error)).toBe(copy.login.tooManyLinks(null));
    expect(copy.login.tooManyLinks(null)).toMatch(/up to an hour/);
  });

  it('asks to try again for anything else', () => {
    expect(signInFailureMessage(new SignInLinkError(SignInRefusal.Unavailable))).toBe(
      copy.login.failed,
    );
    expect(signInFailureMessage(new Error('unexpected'))).toBe(copy.login.failed);
  });
});
