import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { logError } from '../lib/logger';
import type { SupabaseClient } from '@supabase/supabase-js';
import { getSupabaseClient, isConfigured } from '../lib/supabaseClient';
import { AuthContext, type AuthState, type AuthStatus } from './AuthContext';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Holds the Supabase session and keeps it in step with the browser tab.
 *
 * Sign-in is by emailed link, so there is no password anywhere in this app.
 * Which address is allowed in is decided by the database, not here: public
 * sign-ups are off and every table is closed to anyone but the registered
 * owner, so a link sent to a stranger opens an empty, useless page.
 */
/**
 * Finishes a sign-in that arrived as tokens in the address bar.
 *
 * The dashboard asks for links in the safer style, which is tied to the very
 * browser that asked for them. A link made any other way hands the session
 * over after the `#` in the address instead: one issued as a replacement when
 * the daily e-mail allowance runs out, or one opened on a different device
 * from the one that asked. Without this the page ignores it and asks to sign
 * in again, which looks exactly like the link not working.
 *
 * The address is cleaned afterwards so the session key does not sit in the
 * address bar or in the browser's history.
 */
async function completeLinkFromAddress(supabase: SupabaseClient): Promise<void> {
  const fragment = window.location.hash.slice(1);
  if (!fragment.includes('access_token')) return;
  const values = new URLSearchParams(fragment);
  const accessToken = values.get('access_token');
  const refreshToken = values.get('refresh_token');
  if (accessToken === null || refreshToken === null) return;
  const { error } = await supabase.auth.setSession({
    access_token: accessToken,
    refresh_token: refreshToken,
  });
  if (error !== null) logError('auth.link_exchange_failed', { code: error.code ?? null });
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    isConfigured() ? 'loading' : 'not-configured',
  );
  const [email, setEmail] = useState<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (status !== 'signed-out') return;
    // Whoever signs in next on this device must never see this person's data,
    // not even for the moment before their own is fetched. Doing it here, once
    // the screens behind the sign-in guard have gone, covers every way a
    // session can end: signing out, an expired session, another tab.
    queryClient.clear();
  }, [status, queryClient]);

  useEffect(() => {
    if (!isConfigured()) return;

    let active = true;
    const supabase = getSupabaseClient();

    completeLinkFromAddress(supabase)
      .then(() => supabase.auth.getSession())
      .then(({ data }) => {
        if (!active) return;
        setEmail(data.session?.user.email ?? null);
        setStatus(data.session === null ? 'signed-out' : 'signed-in');
      })
      .catch(() => {
        if (!active) return;
        logError('auth.session_read_failed');
        setStatus('signed-out');
      });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      setEmail(session?.user.email ?? null);
      setStatus(session === null ? 'signed-out' : 'signed-in');
    });

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  const sendSignInLink = useCallback(async (address: string) => {
    const supabase = getSupabaseClient();
    const { error } = await supabase.auth.signInWithOtp({
      email: address,
      options: {
        emailRedirectTo: `${window.location.origin}/`,
        // Nobody but the owner may ever get an account from this page.
        shouldCreateUser: false,
      },
    });
    if (error !== null) {
      logError('auth.link_send_failed', { code: error.code ?? null });
      throw new Error('sign-in link could not be sent');
    }
  }, []);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseClient();
    const { error } = await supabase.auth.signOut();
    if (error !== null) logError('auth.sign_out_failed', { code: error.code ?? null });
    setEmail(null);
    setStatus('signed-out');
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, email, sendSignInLink, signOut }),
    [status, email, sendSignInLink, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
