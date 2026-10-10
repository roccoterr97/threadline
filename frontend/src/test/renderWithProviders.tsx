import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, parsePath, Route, Routes, useLocation } from 'react-router-dom';
import { databaseVersionQueryKey } from '../api/databaseVersion';
import { AuthContext, type AuthState } from '../auth/AuthContext';
import { fixedClock, type Clock } from '../lib/clock';
import { ClockContext } from '../lib/ClockContext';
import { NOW } from './__fixtures__/sampleData';

interface RenderOptions {
  /** The address the test starts at. */
  route?: string;
  /**
   * The route pattern `ui` is mounted under, for `useParams`. Pass null when
   * `ui` already contains its own `<Routes>`.
   */
  path?: string | null;
  clock?: Clock;
  auth?: Partial<AuthState>;
  /** Location state the first address carries, as `navigate(to, { state })` would leave it. */
  state?: unknown;
}

/** Prints the current address so a test can assert on the URL. */
function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

function stubAuth(overrides: Partial<AuthState>): AuthState {
  return {
    status: 'signed-in',
    email: 'owner@example.test',
    sendSignInLink: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    ...overrides,
  };
}

interface ProvidersResult extends RenderResult {
  user: ReturnType<typeof userEvent.setup>;
  queryClient: QueryClient;
}

/**
 * Renders a screen with everything it expects around it.
 *
 * Time is frozen and the sign-in state is a stub, so no test depends on the
 * wall clock or on a real Supabase session.
 */
export function renderWithProviders(ui: ReactNode, options: RenderOptions = {}): ProvidersResult {
  const { route = '/', path = '*', clock = fixedClock(NOW), auth = {}, state } = options;
  const firstEntry = state === undefined ? route : { ...parsePath(route), state };

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  // The database counts as up to date, so no screen asks it; the notice that
  // asks has tests of its own.
  queryClient.setQueryData(databaseVersionQueryKey, false);

  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={stubAuth(auth)}>
        <ClockContext.Provider value={clock}>
          <MemoryRouter initialEntries={[firstEntry]}>
            <LocationProbe />
            {path === null ? ui : <Routes>{<Route path={path} element={ui} />}</Routes>}
          </MemoryRouter>
        </ClockContext.Provider>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );

  return { ...result, user: userEvent.setup(), queryClient };
}
