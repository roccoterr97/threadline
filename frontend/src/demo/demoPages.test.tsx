import { render, screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { AppLayout } from '../components/AppLayout';
import * as copy from '../copy/en';
import { fixedClock } from '../lib/clock';
import { HomePage } from '../pages/HomePage';
import { PersonPage } from '../pages/PersonPage';
import { ReviewPage } from '../pages/ReviewPage';
import { RunsPage } from '../pages/RunsPage';
import { SettingsPage } from '../pages/SettingsPage';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/renderWithProviders';
import { SETUP_GUIDE_URL } from './DemoBanner';
import { startDemo } from './startDemo';

const clock = fixedClock(new Date(2026, 8, 29, 10, 0));

/** Every signed-in page, inside the real layout, reading the demo's data. */
function renderDemo(route: string) {
  return renderWithProviders(
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/people/:personId" element={<PersonPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>,
    { route, path: null, clock },
  );
}

beforeEach(() => {
  startDemo(clock);
});

describe('the dashboard in demo mode', () => {
  it('shows the people, the counters and the meetings coming up', async () => {
    renderDemo('/');
    expect(await screen.findAllByText('Maya Lindqvist')).not.toHaveLength(0);
    expect(await screen.findByText(copy.home.comingUp.title)).toBeInTheDocument();
    expect(screen.getAllByText('Prospects').length).toBeGreaterThan(0);
  });

  it('shows a person with their timeline', async () => {
    renderDemo('/people/demo-p02');
    expect(await screen.findByRole('heading', { name: 'Tomás Ferreira' })).toBeInTheDocument();
    expect(await screen.findByText(/revise it before Thursday/)).toBeInTheDocument();
  });

  it('shows the owner\'s notes on a person, with their dates', async () => {
    renderDemo('/people/demo-p01');
    const notes = await screen.findByRole('region', { name: copy.notes.title });
    expect(await within(notes).findByText(/Rotterdam logistics fair/)).toBeInTheDocument();
    expect(within(notes).getAllByText(/^Written /)).toHaveLength(2);
    expect(within(notes).getAllByText(/^changed /)).toHaveLength(1);
  });

  it('shows the open questions', async () => {
    renderDemo('/review');
    const question = 'Is Marcus Bell part of your sales outreach?';
    expect(await screen.findByText(question)).toBeInTheDocument();
  });

  it('shows the run history', async () => {
    renderDemo('/runs');
    expect(await screen.findByRole('heading', { name: copy.runs.title })).toBeInTheDocument();
    expect(await screen.findAllByText(copy.runErrors.source_unavailable!)).not.toHaveLength(0);
  });

  it('shows the categories and a one-tap suggestion on the settings page', async () => {
    renderDemo('/settings');
    const main = await screen.findByRole('main');
    expect(await within(main).findAllByText(/Partners/)).not.toHaveLength(0);
    const addReferrer = copy.categorySettings.actions.addSuggestion('Referrer');
    expect(await within(main).findByRole('button', { name: addReferrer })).toBeInTheDocument();
  });
});

describe('the browser tab in demo mode', () => {
  it.each([
    ['/', copy.home.title],
    ['/review', copy.review.title],
    ['/runs', copy.runs.title],
    ['/settings', copy.settings.title],
  ])('names %s after its page', async (route, page) => {
    renderDemo(route);
    await screen.findByRole('heading', { level: 1, name: page });
    expect(document.title).toBe(copy.app.pageTitle(page));
  });
});

describe('the demo banner', () => {
  it('says the data is made up and links to the setup guide', async () => {
    const { container } = render(startDemo(clock).banner);
    expect(screen.getByText(copy.demo.notice)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.demo.setupLink })).toHaveAttribute(
      'href',
      SETUP_GUIDE_URL,
    );
    await expectNoAxeViolations(container);
  });
});
