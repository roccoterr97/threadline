import { lazy } from 'react';
import { Route, Routes } from 'react-router-dom';
import { SiteLayout } from './components/SiteLayout';

// Split per page: the home page should not download the whole guide first.
const HomePage = lazy(async () => ({ default: (await import('./pages/HomePage')).HomePage }));
const SetupStartPage = lazy(async () => ({
  default: (await import('./pages/SetupStartPage')).SetupStartPage,
}));
const SetupComputerPage = lazy(async () => ({
  default: (await import('./pages/SetupComputerPage')).SetupComputerPage,
}));
const SetupWayPage = lazy(async () => ({ default: (await import('./pages/SetupWayPage')).SetupWayPage }));
const SetupClaudePage = lazy(async () => ({
  default: (await import('./pages/SetupClaudePage')).SetupClaudePage,
}));
const SetupChoicePage = lazy(async () => ({
  default: (await import('./pages/SetupChoicePage')).SetupChoicePage,
}));
const SetupStepPage = lazy(async () => ({ default: (await import('./pages/SetupStepPage')).SetupStepPage }));
const SetupDonePage = lazy(async () => ({ default: (await import('./pages/SetupDonePage')).SetupDonePage }));
const SetupExtraPage = lazy(async () => ({
  default: (await import('./pages/SetupExtraPage')).SetupExtraPage,
}));
const DashboardPage = lazy(async () => ({
  default: (await import('./pages/DashboardPage')).DashboardPage,
}));
const UpdatePage = lazy(async () => ({ default: (await import('./pages/UpdatePage')).UpdatePage }));
const QuestionsPage = lazy(async () => ({
  default: (await import('./pages/QuestionsPage')).QuestionsPage,
}));
const PrivacyPage = lazy(async () => ({ default: (await import('./pages/PrivacyPage')).PrivacyPage }));
const NotFoundPage = lazy(async () => ({
  default: (await import('./pages/NotFoundPage')).NotFoundPage,
}));

/** Every page of the website. */
export function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/setup" element={<SetupStartPage />} />
        <Route path="/setup/computer" element={<SetupComputerPage />} />
        <Route path="/setup/way" element={<SetupWayPage />} />
        <Route path="/setup/claude" element={<SetupClaudePage />} />
        <Route path="/setup/choose/:choiceId" element={<SetupChoicePage />} />
        <Route path="/setup/step/:stepId" element={<SetupStepPage />} />
        <Route path="/setup/done" element={<SetupDonePage />} />
        <Route path="/setup/extra/:partId" element={<SetupExtraPage />} />
        <Route path="/app" element={<DashboardPage />} />
        <Route path="/update" element={<UpdatePage />} />
        <Route path="/questions" element={<QuestionsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
