import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories } from '../api/categories';
import { markPersonAsRelevant } from '../api/overrides';
import { fetchPeople } from '../api/people';
import { fetchStatusLabels } from '../api/statusLabels';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { hiddenPersonState } from '../lib/hiddenPerson';
import { ORGANISATION_ROUTE, organisationsListState } from '../lib/organisationAddress';
import { expectNoAxeViolations } from '../test/axe';
import {
  sampleCategories,
  samplePeople,
  sampleStatusLabels,
} from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { OrganisationPage } from './OrganisationPage';

vi.mock('../api/people', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/people')>()),
  fetchPeople: vi.fn(),
}));

vi.mock('../api/overrides', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/overrides')>()),
  markPersonAsRelevant: vi.fn(),
}));

vi.mock('../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categories')>()),
  fetchCategories: vi.fn(),
}));

vi.mock('../api/statusLabels', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/statusLabels')>()),
  fetchStatusLabels: vi.fn(),
}));

const fetchPeopleMock = vi.mocked(fetchPeople);
const fetchCategoriesMock = vi.mocked(fetchCategories);
const fetchStatusLabelsMock = vi.mocked(fetchStatusLabels);

/** Ben (waiting on them) moved in with Ana (the owner's turn) at Northwind Labs. */
const NORTHWIND_OF_TWO = samplePeople.map((person) =>
  person.person_id === 'p-02' ? { ...person, organisation_name: 'Northwind Labs' } : person,
);

/** The page at `route`, with both organisation routes mounted, as the app has them. */
function renderPage(route: string, state?: unknown) {
  return renderWithProviders(
    <Routes>
      <Route path={ORGANISATION_ROUTE} element={<OrganisationPage />} />
      <Route path="/organisations/none" element={<OrganisationPage />} />
      <Route path="/people/:personId" element={<p>Person page</p>} />
      <Route path="/organisations" element={<p>Organisations list</p>} />
    </Routes>,
    { route, path: null, state },
  );
}

/** The wide-screen people table on the page. */
async function peopleTable(): Promise<HTMLElement> {
  return screen.findByRole('table', { name: copy.home.tableCaption });
}

function backLink(): HTMLElement {
  return screen.getByRole('link', { name: copy.organisations.backToOrganisations });
}

beforeEach(() => {
  fetchPeopleMock.mockResolvedValue(NORTHWIND_OF_TWO);
  fetchCategoriesMock.mockResolvedValue(sampleCategories);
  fetchStatusLabelsMock.mockResolvedValue(sampleStatusLabels);
});

describe('OrganisationPage — the four states', () => {
  it('says what it is loading', () => {
    fetchPeopleMock.mockReturnValue(new Promise(() => undefined));
    renderPage('/organisations/name/Northwind%20Labs');
    expect(screen.getByText(copy.organisations.loading)).toBeInTheDocument();
  });

  it('explains an organisation that is not there, with a way back', async () => {
    renderPage('/organisations/name/Nowhere', organisationsListState('?sort=name'));
    expect(await screen.findByText(copy.organisations.notFound.title)).toBeInTheDocument();
    expect(backLink()).toHaveAttribute('href', '/organisations?sort=name');
  });

  it('offers a retry when the people cannot be loaded', async () => {
    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    const { user } = renderPage('/organisations/name/Northwind%20Labs');
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();

    fetchPeopleMock.mockResolvedValue(NORTHWIND_OF_TWO);
    await user.click(screen.getByRole('button', { name: copy.states.retry }));
    expect(await peopleTable()).toBeInTheDocument();
  });

  it('offers a retry when the categories cannot be loaded', async () => {
    fetchCategoriesMock.mockRejectedValue(new DataUnavailableError('categories.list'));
    renderPage('/organisations/name/Northwind%20Labs');
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.states.retry })).toBeInTheDocument();
  });

  it('shows the organisation, its picture and its people in the people rows', async () => {
    renderPage('/organisations/name/Northwind%20Labs');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Northwind Labs' }),
    ).toBeInTheDocument();
    expect(document.title).toBe(copy.app.pageTitle('Northwind Labs'));
    expect(screen.getByText(/2 people you are in touch with here/)).toBeInTheDocument();

    const picture = screen.getByRole('group', { name: copy.organisations.stateGroupLabel });
    expect(
      within(picture).getByText(copy.organisations.stateCount(copy.waitingOnBadges.me, 1)),
    ).toBeInTheDocument();

    const table = await peopleTable();
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByRole('link', { name: 'Ana Ruiz' })).toHaveAttribute(
      'href',
      '/people/p-01',
    );
    expect(within(table).getByRole('link', { name: 'Ben Okafor' })).toBeInTheDocument();
  });
});

describe('OrganisationPage — a name that needs escaping', () => {
  it('finds the organisation behind an escaped address', async () => {
    renderPage('/organisations/name/Slate%20%26%20Sons');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Slate & Sons' }),
    ).toBeInTheDocument();
    expect(within(await peopleTable()).getByRole('link', { name: 'Hugo Prieto' })).toBeInTheDocument();
  });
});

describe('OrganisationPage — the people with no organisation', () => {
  it('shows them under a clear heading with an explanation', async () => {
    renderPage('/organisations/none');
    expect(
      await screen.findByRole('heading', { level: 1, name: copy.organisations.noOrganisation }),
    ).toBeInTheDocument();
    expect(screen.getByText(/People with no organisation on record/)).toBeInTheDocument();
    expect(within(await peopleTable()).getAllByRole('row')).toHaveLength(4);
  });
});

describe('OrganisationPage — the ways back', () => {
  it('goes back to the list with the filters and order it was opened from', async () => {
    renderPage('/organisations/name/Northwind%20Labs', organisationsListState('?waiting=me'));
    await peopleTable();
    expect(backLink()).toHaveAttribute('href', '/organisations?waiting=me');
  });

  it('goes back to the plain list when opened some other way', async () => {
    renderPage('/organisations/name/Northwind%20Labs');
    await peopleTable();
    expect(backLink()).toHaveAttribute('href', '/organisations');
  });

  it('opens a person and comes back here, keeping the list view, from the person page', async () => {
    const { user } = renderPage(
      '/organisations/name/Northwind%20Labs',
      organisationsListState('?sort=name'),
    );
    await user.click(within(await peopleTable()).getByRole('link', { name: 'Ana Ruiz' }));
    expect(await screen.findByText('Person page')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/people/p-01');
  });
});

describe('OrganisationPage — after hiding someone', () => {
  it('says who was hidden, without them in the list, and still leads back to the same view', async () => {
    const hidden = { id: 'p-02', name: 'Ben Okafor' };
    fetchPeopleMock.mockResolvedValue(
      NORTHWIND_OF_TWO.filter((person) => person.person_id !== hidden.id),
    );
    renderPage('/organisations/name/Northwind%20Labs', {
      ...organisationsListState('?sort=name'),
      ...hiddenPersonState(hidden),
    });

    expect(await screen.findByText(copy.person.hidden.notice(hidden.name))).toBeInTheDocument();
    const table = await peopleTable();
    expect(within(table).queryByRole('link', { name: hidden.name })).not.toBeInTheDocument();
    expect(backLink()).toHaveAttribute('href', '/organisations?sort=name');
  });

  it('puts the person back from the note', async () => {
    const hidden = { id: 'p-02', name: 'Ben Okafor' };
    vi.mocked(markPersonAsRelevant).mockResolvedValue(undefined);
    fetchPeopleMock.mockResolvedValue(
      NORTHWIND_OF_TWO.filter((person) => person.person_id !== hidden.id),
    );
    const { user } = renderPage('/organisations/name/Northwind%20Labs', hiddenPersonState(hidden));
    await screen.findByText(copy.person.hidden.notice(hidden.name));

    fetchPeopleMock.mockResolvedValue(NORTHWIND_OF_TWO);
    await user.click(screen.getByRole('button', { name: copy.person.hidden.undoLabel(hidden.name) }));

    expect(await screen.findByText(copy.person.hidden.restored(hidden.name))).toBeInTheDocument();
    expect(
      await within(await peopleTable()).findByRole('link', { name: hidden.name }),
    ).toBeInTheDocument();
  });

  it('still shows the note when the organisation emptied out', async () => {
    const hidden = { id: 'p-08', name: 'Hugo Prieto' };
    fetchPeopleMock.mockResolvedValue(
      NORTHWIND_OF_TWO.filter((person) => person.person_id !== hidden.id),
    );
    renderPage('/organisations/name/Slate%20%26%20Sons', hiddenPersonState(hidden));

    expect(await screen.findByText(copy.person.hidden.notice(hidden.name))).toBeInTheDocument();
    expect(screen.getByText(copy.organisations.notFound.title)).toBeInTheDocument();
  });
});

describe('OrganisationPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderPage('/organisations/name/Northwind%20Labs');
    await peopleTable();
    await expectNoAxeViolations(container);
  });
});
