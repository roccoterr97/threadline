import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { EmptyState } from '../components/EmptyState';
import { LoadingState } from '../components/LoadingState';
import * as copy from '../copy/en';
import { useAuth } from './useAuth';

interface RequireAuthProps {
  children: ReactNode;
}

/**
 * The route guard.
 *
 * Nothing behind it renders until Supabase has confirmed a session, so a signed
 * out visitor never sees a flash of the dashboard before the redirect.
 */
export function RequireAuth({ children }: RequireAuthProps) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'not-configured') {
    return (
      <main className="mx-auto max-w-prose px-4 py-10">
        <EmptyState title={copy.states.errorTitle} body={copy.states.notConfigured} />
      </main>
    );
  }

  if (status === 'loading') {
    return (
      <main className="mx-auto max-w-prose px-4 py-10">
        <LoadingState label={copy.login.checkingSession} />
      </main>
    );
  }

  if (status === 'signed-out') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}
