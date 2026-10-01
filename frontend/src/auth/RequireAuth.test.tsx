import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { renderWithProviders } from '../test/renderWithProviders';
import { RequireAuth } from './RequireAuth';

const SECRET = 'The owner’s people';

function renderGuard(route: string, status: 'loading' | 'signed-in' | 'signed-out') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<p>{copy.login.title}</p>} />
      <Route
        path="/runs"
        element={
          <RequireAuth>
            <p>{SECRET}</p>
          </RequireAuth>
        }
      />
    </Routes>,
    { route, path: null, auth: { status, email: status === 'signed-in' ? 'x@y.test' : null } },
  );
}

describe('RequireAuth', () => {
  it('sends a signed-out visitor to the sign-in page', () => {
    renderGuard('/runs', 'signed-out');
    expect(screen.getByText(copy.login.title)).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/login');
  });

  it('shows nothing of the dashboard while the session is being checked', () => {
    renderGuard('/runs', 'loading');
    expect(screen.getByText(copy.login.checkingSession)).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
  });

  it('lets the owner through once the session is confirmed', () => {
    renderGuard('/runs', 'signed-in');
    expect(screen.getByText(SECRET)).toBeInTheDocument();
  });
});
