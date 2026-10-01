import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setSession = vi.fn();
const getSession = vi.fn();

vi.mock('../lib/supabaseClient', () => ({
  isConfigured: () => true,
  getSupabaseClient: () => ({
    auth: {
      setSession,
      getSession,
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
    },
  }),
}));

const { AuthProvider } = await import('./AuthProvider');
const { useAuth } = await import('./useAuth');

function Probe() {
  const { status } = useAuth();
  return <p>{status}</p>;
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
    );

    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
    expect(setSession).not.toHaveBeenCalled();
  });
});
