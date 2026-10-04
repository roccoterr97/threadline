import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { AppLayout } from '../components/AppLayout';
import * as copy from '../copy/en';
import { fixedClock } from '../lib/clock';
import { ORGANISATION_ROUTE } from '../lib/organisationAddress';
import { OrganisationPage } from '../pages/OrganisationPage';
import { OrganisationsPage } from '../pages/OrganisationsPage';
import { PersonPage } from '../pages/PersonPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { startDemo } from './startDemo';

const clock = fixedClock(new Date(2026, 8, 29, 10, 0));

/** The organisation pages inside the real layout, reading the demo's data. */
function renderDemo(route: string) {
  return renderWithProviders(
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/organisations" element={<OrganisationsPage />} />
        <Route path={ORGANISATION_ROUTE} element={<OrganisationPage />} />
        <Route path="/organisations/none" element={<OrganisationPage />} />
        <Route path="/people/:personId" element={<PersonPage />} />
      </Route>
    </Routes>,
    { route, path: null, clock },
  );
}

beforeEach(() => {
  startDemo(clock);
});

describe('the organisations in demo mode', () => {
  it('lists the invented organisations, the one with two people first', async () => {
    renderDemo('/organisations');
    const table = await screen.findByRole('table', { name: copy.organisations.tableCaption });
    const names = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => within(row).getByRole('link').textContent);
    expect(names[0]).toBe('Stackbridge Integrations');
    expect(names).toContain('Bellwether Clinics');
    expect(names).not.toContain('Northgate Print');
    expect(names.at(-1)).toBe(copy.organisations.noOrganisation);
    const bellwether = within(table).getByRole('link', { name: 'Bellwether Clinics' }).closest('tr')!;
    expect(within(bellwether).getByText(copy.organisations.peopleCount(2))).toBeInTheDocument();
    expect(document.title).toBe(copy.app.pageTitle(copy.organisations.title));
  });

  it('shows one organisation with its people, each opening the person', async () => {
    const { user } = renderDemo('/organisations/name/Stackbridge%20Integrations');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Stackbridge Integrations' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 people you are in touch with here/)).toBeInTheDocument();

    const table = await screen.findByRole('table', { name: copy.home.tableCaption });
    await user.click(within(table).getByRole('link', { name: 'Rafael Ortega' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Rafael Ortega' })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: copy.organisations.backToOrganisation('Stackbridge Integrations') }),
    ).toHaveAttribute('href', '/organisations/name/Stackbridge%20Integrations');
  });

  it('shows the people with no organisation on their own page', async () => {
    renderDemo('/organisations/none');
    expect(
      await screen.findByRole('heading', { level: 1, name: copy.organisations.noOrganisation }),
    ).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(within(table).getByRole('link', { name: 'Jonah Whitfield' })).toBeInTheDocument();
  });
});
