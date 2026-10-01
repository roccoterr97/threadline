import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { App } from '../App';
import { AuthProvider } from '../auth/AuthProvider';
import * as copy from '../copy/en';
import { fixedClock } from '../lib/clock';
import { ClockContext } from '../lib/ClockContext';
import { expectNoAxeViolations } from '../test/axe';
import { startDemo } from './startDemo';

const clock = fixedClock(new Date(2026, 8, 29, 10, 0));

/** The whole dashboard as the demo build runs it: real sign-in provider, demo stand-in. */
function renderDemoApp(route: string) {
  const parts = startDemo(clock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ClockContext.Provider value={clock}>
          <MemoryRouter initialEntries={[route]}>
            <App banner={parts.banner} signInPage={parts.signInPage} />
          </MemoryRouter>
        </ClockContext.Provider>
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { ...result, user: userEvent.setup() };
}

describe('signing out of the demo', () => {
  it('shows the demo sign-in instead of the e-mail form, and signs back in with one tap', async () => {
    const { user, container } = renderDemoApp('/runs');
    await screen.findByRole('heading', { name: copy.runs.title });
    expect(screen.getByText(copy.demo.notice)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: copy.nav.signOut }));

    expect(
      await screen.findByRole('heading', { name: copy.demo.signedOut.title }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(copy.login.emailLabel)).not.toBeInTheDocument();
    expect(screen.getByText(copy.demo.notice)).toBeInTheDocument();
    await expectNoAxeViolations(container);

    await user.click(screen.getByRole('button', { name: copy.demo.signedOut.signIn }));

    expect(await screen.findByRole('heading', { name: copy.home.title })).toBeInTheDocument();
  });
});
