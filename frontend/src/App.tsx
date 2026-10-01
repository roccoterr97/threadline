import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage } from './auth/LoginPage';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './components/AppLayout';
import { LoadingState } from './components/LoadingState';
import * as copy from './copy/en';

// Split per route: opening the dashboard on a phone should not download the
// person page, the review list and the run history first.
const HomePage = lazy(async () => ({ default: (await import('./pages/HomePage')).HomePage }));
const PersonPage = lazy(async () => ({ default: (await import('./pages/PersonPage')).PersonPage }));
const ReviewPage = lazy(async () => ({ default: (await import('./pages/ReviewPage')).ReviewPage }));
const RunsPage = lazy(async () => ({ default: (await import('./pages/RunsPage')).RunsPage }));
const SettingsPage = lazy(async () => ({
  default: (await import('./pages/SettingsPage')).SettingsPage,
}));

/** Pieces a special build (the demo) puts in place of the usual ones. */
export interface AppParts {
  /** A strip shown above every signed-in page, after the "skip" link. */
  banner?: ReactNode;
  /** Shown at `/login` instead of the e-mail sign-in form. */
  signInPage?: ReactNode;
}

/** Every route in the dashboard. */
export function App({ banner, signInPage }: AppParts = {}) {
  return (
    <Suspense fallback={<LoadingState label={copy.states.loading} />}>
      <Routes>
        <Route path="/login" element={signInPage ?? <LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout banner={banner} />
            </RequireAuth>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/people/:personId" element={<PersonPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
