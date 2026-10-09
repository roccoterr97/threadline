import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { AuthApiError } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignInLinkError, SignInRefusal } from '../lib/errors';

const setSession = vi.fn();
const getSession = vi.fn();
const signOut = vi.fn();
const signInWithOtp = vi.fn();
let announce: (event: string, session: unknown) => void = () => undefined;

vi.mock('../lib/supabaseClient', () => ({
  isConfigured: () => true,
  getSupabaseClient: () => ({
    auth: {
      setSession,
      getSession,
      signOut,
      signInWithOtp,
      onAuthStateChange: (listener: typeof announce) => {
        announce = listener;
        return { data: { subscription: { unsubscribe: () => undefined } } };
      },
    },
  }),
}));

const { AuthProvider } = await import('./AuthProvider');
const { useAuth } = await import('./useAuth');

function Probe() {
  const { status } = useAuth();
  return <p>{status}</p>;
}

function SignOutButton() {
  const { signOut: leave } = useAuth();
  return (
    <button
      type="button"
      onClick={() => {
        void leave();
      }}
    >
      leave
    </button>
  );
}

function SendLinkButton({ onResult }: { onResult: (outcome: unknown) => void }) {
  const { sendSignInLink } = useAuth();
  return (
    <button
      type="button"
      onClick={() => {
        sendSignInLink('stranger@example.test').then(onResult, onResult);
      }}
    >
      send
    </button>
  );
}

function withQueryClient(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('finishing a sign-in link', () => {
  beforeEach(() => {
    setSession.mockReset().mockResolvedValue({ error: null });
    getSession.mockReset().mockResolvedValue({ data: { session: null } });
    window.history.replaceState(null, '', '/');
  });

  it('accepts a link that carries the session in the address', async () => {
    // A link issued outside the browser that asked for it - a replacement made
    // when the e-mail allowance runs out, or one opened on another device.
    window.location.hash =
      '#access_token=the-access-token&refresh_token=the-refresh-token&token_type=bearer';

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
      { wrapper: withQueryClient(new QueryClient()) },
    );

    await waitFor(() =>
      expect(setSession).toHaveBeenCalledWith({
        access_token: 'the-access-token',
        refresh_token: 'the-refresh-token',
      }),
    );
    await waitFor(() => expect(window.location.hash).toBe(''));
  });

  it('leaves an ordinary visit alone', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
      { wrapper: withQueryClient(new QueryClient()) },
    );

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
    expect(setSession).not.toHaveBeenCalled();
  });
});

describe('what is kept in memory when someone leaves', () => {
  const OWNER_SESSION = { user: { email: 'owner@example.test' } };
  const PRIVATE_KEY = ['people'];

  function renderSignedIn() {
    const queryClient = new QueryClient();
    queryClient.setQueryData(PRIVATE_KEY, ['the previous person\'s data']);
    getSession.mockResolvedValue({ data: { session: OWNER_SESSION } });
    render(
      <AuthProvider>
        <Probe />
        <SignOutButton />
      </AuthProvider>,
      { wrapper: withQueryClient(queryClient) },
    );
    return queryClient;
  }

  beforeEach(() => {
    getSession.mockReset();
    signOut.mockReset().mockResolvedValue({ error: null });
    window.history.replaceState(null, '', '/');
  });

  it('keeps the data while the owner stays signed in', async () => {
    const queryClient = renderSignedIn();
    await waitFor(() => expect(screen.getByText('signed-in')).toBeInTheDocument());
    expect(queryClient.getQueryData(PRIVATE_KEY)).toBeDefined();
  });

  it('forgets every cached answer when the owner signs out', async () => {
    const queryClient = renderSignedIn();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText('signed-in')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'leave' }));

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
    await waitFor(() => {
      expect(queryClient.getQueryData(PRIVATE_KEY)).toBeUndefined();
    });
  });

  it('forgets them too when the session ends some other way', async () => {
    const queryClient = renderSignedIn();
    await waitFor(() => expect(screen.getByText('signed-in')).toBeInTheDocument());

    act(() => {
      announce('SIGNED_OUT', null);
    });

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
    await waitFor(() => {
      expect(queryClient.getQueryData(PRIVATE_KEY)).toBeUndefined();
    });
  });

  it('forgets them even when the sign-out request itself fails', async () => {
    signOut.mockResolvedValue({ error: { code: 'network', message: 'offline' } });
    const queryClient = renderSignedIn();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText('signed-in')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'leave' }));

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
    await waitFor(() => {
      expect(queryClient.getQueryData(PRIVATE_KEY)).toBeUndefined();
    });
  });
});

describe('asking for a sign-in link', () => {
  beforeEach(() => {
    getSession.mockReset().mockResolvedValue({ data: { session: null } });
    signInWithOtp.mockReset();
    window.history.replaceState(null, '', '/');
  });

  it('never creates a login and says why Supabase refused the address', async () => {
    signInWithOtp.mockResolvedValue({
      data: { user: null, session: null },
      error: new AuthApiError('Signups not allowed for otp', 422, 'otp_disabled'),
    });
    const onResult = vi.fn();
    render(
      <AuthProvider>
        <Probe />
        <SendLinkButton onResult={onResult} />
      </AuthProvider>,
      { wrapper: withQueryClient(new QueryClient()) },
    );
    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());

    await userEvent.setup().click(screen.getByRole('button', { name: 'send' }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());
    expect(signInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({ options: expect.objectContaining({ shouldCreateUser: false }) }),
    );
    const outcome: unknown = onResult.mock.calls[0]?.[0];
    expect(outcome).toBeInstanceOf(SignInLinkError);
    expect(outcome).toMatchObject({ reason: SignInRefusal.UnknownAddress });
  });
});
