import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories } from '../api/categories';
import { fetchPeople } from '../api/people';
import { fetchStatusLabels } from '../api/statusLabels';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import {
  sampleCategories,
  samplePeople,
  samplePerson,
  sampleStatusLabels,
} from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { OrganisationsPage } from './OrganisationsPage';

vi.mock('../api/people', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/people')>()),
  fetchPeople: vi.fn(),
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

function renderPage(route = '/organisations') {
  return renderWithProviders(<OrganisationsPage />, { route, path: '/organisations' });
}

/** The wide-screen table of organisations. */
async function organisationsTable(): Promise<HTMLElement> {
  return screen.findByRole('table', { name: copy.organisations.tableCaption });
}

/** The names in the table, top to bottom. */
async function shownNames(): Promise<string[]> {
  const rows = within(await organisationsTable()).getAllByRole('row').slice(1);
  return rows.map((row) => within(row).getByRole('link').textContent ?? '');
}

beforeEach(() => {
  fetchPeopleMock.mockResolvedValue(samplePeople);
  fetchCategoriesMock.mockResolvedValue(sampleCategories);
  fetchStatusLabelsMock.mockResolvedValue(sampleStatusLabels);
});

describe('OrganisationsPage — the four states', () => {
  it('says what it is loading while it waits', () => {
    fetchPeopleMock.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByText(copy.organisations.loading)).toBeInTheDocument();
  });

  it('explains an empty database instead of showing a bare page', async () => {
    fetchPeopleMock.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(copy.home.empty.title)).toBeInTheDocument();
  });

  it('offers a retry when the database cannot be reached', async () => {
    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    const { user } = renderPage();
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();

    fetchPeopleMock.mockResolvedValue(samplePeople);
    await user.click(screen.getByRole('button', { name: copy.states.retry }));
    expect(await organisationsTable()).toBeInTheDocument();
  });

  it('offers a retry when the categories cannot be loaded', async () => {
    fetchCategoriesMock.mockRejectedValue(new DataUnavailableError('categories.list'));
    const { user } = renderPage();
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();

    fetchCategoriesMock.mockResolvedValue(sampleCategories);
    await user.click(screen.getByRole('button', { name: copy.states.retry }));
    expect(await organisationsTable()).toBeInTheDocument();
  });

  it('lists the organisations once they arrive, those needing the owner first', async () => {
    renderPage();
    expect(await shownNames()).toEqual([
      'Harbourline',
      'Northwind Labs',
      'Rowan Partners',
      'Duskwell',
      'Brightfield Ventures',
      'Palegreen',
      'Slate & Sons',
      'Kestrel Capital',
      'Ashford Search',
      copy.organisations.noOrganisation,
    ]);
  });
});

describe('OrganisationsPage — one row', () => {
  /** The table row of one organisation. */
  async function rowOf(name: string): Promise<HTMLElement> {
    const link = within(await organisationsTable()).getByRole('link', { name });
    return link.closest('tr')!;
  }

  it('says how many people are there and when the last contact was', async () => {
    fetchPeopleMock.mockResolvedValue(NORTHWIND_OF_TWO);
    renderPage();
    const row = await rowOf('Northwind Labs');
    expect(within(row).getByText(copy.organisations.peopleCount(2))).toBeInTheDocument();
    expect(within(row).getByText(copy.time.hoursAgo(16))).toBeInTheDocument();
  });

  it('shows the picture in the same words as the people rows, above zero only', async () => {
    fetchPeopleMock.mockResolvedValue(NORTHWIND_OF_TWO);
    renderPage();
    const row = await rowOf('Northwind Labs');
    expect(
      within(row).getByText(copy.organisations.stateCount(copy.waitingOnBadges.me, 1)),
    ).toBeInTheDocument();
    expect(
      within(row).getByText(copy.organisations.stateCount(copy.waitingOnBadges.them, 1)),
    ).toBeInTheDocument();
    expect(within(row).queryByText(/^Overdue/)).not.toBeInTheDocument();
  });

  it('flags a late reply the owner owes in the same words as the person row', async () => {
    renderPage();
    const row = await rowOf('Harbourline');
    expect(
      within(row).getByText(copy.organisations.stateCount(copy.dueBadgeLabels.overdue, 1)),
    ).toBeInTheDocument();
  });

  it('says nobody is waiting when that is so, and "not looked at" when nobody has been', async () => {
    fetchPeopleMock.mockResolvedValue([
      samplePerson('p-06'),
      { ...samplePerson('p-01'), waiting_on: null },
    ]);
    renderPage();
    expect(
      within(await rowOf('Kestrel Capital')).getByText(copy.waitingOnBadges.nobody),
    ).toBeInTheDocument();
    expect(
      within(await rowOf('Northwind Labs')).getByText(copy.values.notAssessed),
    ).toBeInTheDocument();
  });

  it('links each organisation to its own page', async () => {
    renderPage();
    const table = await organisationsTable();
    expect(within(table).getByRole('link', { name: 'Slate & Sons' })).toHaveAttribute(
      'href',
      '/organisations/name/Slate%20%26%20Sons',
    );
    expect(
      within(table).getByRole('link', { name: copy.organisations.noOrganisation }),
    ).toHaveAttribute('href', '/organisations/none');
  });
});

describe('OrganisationsPage — filters and order in the address', () => {
  it('keeps an organisation where someone fits every filter', async () => {
    const { user } = renderPage();
    await organisationsTable();

    await user.click(screen.getByRole('button', { name: 'Investors' }));
    await user.selectOptions(screen.getByLabelText(copy.home.waitingFilterLabel), 'me');

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/organisations?type=vc&waiting=me');
    });
    expect(await shownNames()).toEqual(['Rowan Partners']);
  });

  it('comes back to the same view after a reload of that address', async () => {
    renderPage('/organisations?due=overdue&sort=name');
    expect(await shownNames()).toEqual(['Harbourline', copy.organisations.noOrganisation]);
    expect(screen.getByLabelText(copy.home.dueFilterLabel)).toHaveValue('overdue');
    expect(screen.getByLabelText(copy.home.sortLabel)).toHaveValue('name');
  });

  it('changes the order from the sort control', async () => {
    const { user } = renderPage();
    await organisationsTable();

    await user.selectOptions(screen.getByLabelText(copy.home.sortLabel), 'name');

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/organisations?sort=name');
    });
    expect((await shownNames()).slice(0, 2)).toEqual(['Ashford Search', 'Brightfield Ventures']);
  });

  it('clears every filter from the empty state, keeping the order', async () => {
    const { user } = renderPage('/organisations?type=vc&due=overdue&sort=name');
    expect(await screen.findByText(copy.organisations.emptyFiltered.title)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: copy.home.emptyFiltered.action }));

    expect(await organisationsTable()).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/organisations?sort=name');
  });

  it('takes the list view along when an organisation is opened', async () => {
    renderPage('/organisations?sort=name');
    const table = await organisationsTable();
    expect(within(table).getByRole('link', { name: 'Duskwell' })).toBeInTheDocument();
    // The state itself is checked on the organisation page; here the link exists and points right.
    expect(within(table).getByRole('link', { name: 'Duskwell' })).toHaveAttribute(
      'href',
      '/organisations/name/Duskwell',
    );
  });
});

describe('OrganisationsPage — the phone switch', () => {
  it('leads between the two views and marks this one', async () => {
    renderPage();
    await organisationsTable();
    const nav = screen.getByRole('navigation', { name: copy.organisations.switchLabel });
    expect(within(nav).getByRole('link', { name: copy.nav.home })).toHaveAttribute('href', '/');
    expect(within(nav).getByRole('link', { name: copy.nav.organisations })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});

describe('OrganisationsPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderPage('/organisations?waiting=me');
    await organisationsTable();
    await expectNoAxeViolations(container);
  });
});
