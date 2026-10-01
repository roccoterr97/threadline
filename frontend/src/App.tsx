import { lazy, Suspense } from 'react';
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

/** Every route in the dashboard. */
export function App() {
  return (
    <Suspense fallback={<LoadingState label={copy.states.loading} />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
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
