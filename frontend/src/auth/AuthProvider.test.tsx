import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setSession = vi.fn();
const getSession = vi.fn();
const signOut = vi.fn();
let announce: (event: string, session: unknown) => void = () => undefined;

vi.mock('../lib/supabaseClient', () => ({
  isConfigured: () => true,
  getSupabaseClient: () => ({
    auth: {
      setSession,
      getSession,
      signOut,
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
