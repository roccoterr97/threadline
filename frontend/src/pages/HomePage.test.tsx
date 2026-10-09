import { act, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories } from '../api/categories';
import { fetchUpcomingMeetings } from '../api/meetings';
import { fetchPeople, peopleQueryKey } from '../api/people';
import { fetchRecentRuns } from '../api/runs';
import { fetchStatusLabels } from '../api/statusLabels';
import { PEOPLE_MAX_ROWS } from '../constants/dashboard';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import {
  NOW,
  peopleWithCategories,
  salesCategories,
  sampleCategories,
  sampleMeetings,
  samplePeople,
  sampleRuns,
  sampleStatusLabels,
  singleCategory,
  withArchived,
} from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { HomePage } from './HomePage';

vi.mock('../api/people', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/people')>()),
  fetchPeople: vi.fn(),
}));

vi.mock('../api/runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/runs')>()),
  fetchRecentRuns: vi.fn(),
}));

vi.mock('../api/meetings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/meetings')>()),
  fetchUpcomingMeetings: vi.fn(),
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
const fetchRunsMock = vi.mocked(fetchRecentRuns);
const fetchMeetingsMock = vi.mocked(fetchUpcomingMeetings);

/** The link behind one headline counter, found inside the counters list. */
function counterLink(label: string): HTMLElement {
  const list = screen.getByRole('list', { name: copy.home.countersLabel });
  return within(list).getByRole('link', { name: new RegExp(`^${label}`) });
}

/** Reads the number printed under a counter's label. */
function counterValue(label: string): string {
  const text = counterLink(label).textContent ?? '';
  return text.replace(label, '').replace(copy.home.counterShown, '');
}

/** The "Coming up" strip, found by its heading. */
function comingUp(): HTMLElement {
  return screen.getByRole('region', { name: copy.home.comingUp.title });
}

/** The wide-screen people table (the status grid is a table too). */
function peopleTable(): HTMLElement {
  return screen.getByRole('table', { name: copy.home.tableCaption });
}

/** Counts the people shown, using the wide-screen table. */
function shownPeople(): number {
  return within(peopleTable()).getAllByRole('row').length - 1;
}

beforeEach(() => {
  fetchPeopleMock.mockResolvedValue(samplePeople);
  fetchRunsMock.mockResolvedValue(sampleRuns);
  fetchMeetingsMock.mockResolvedValue([]);
  fetchCategoriesMock.mockResolvedValue(sampleCategories);
  fetchStatusLabelsMock.mockResolvedValue(sampleStatusLabels);
});

describe('HomePage — the four states', () => {
  it('says what it is loading while it waits', () => {
    fetchPeopleMock.mockReturnValue(new Promise(() => undefined));
    renderWithProviders(<HomePage />);
    expect(screen.getByText(copy.states.loadingPeople)).toBeInTheDocument();
  });

  it('explains an empty database instead of showing a bare page', async () => {
    fetchPeopleMock.mockResolvedValue([]);
    renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.home.empty.title)).toBeInTheDocument();
  });

  it('offers a retry when the database cannot be reached', async () => {
    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    const { user } = renderWithProviders(<HomePage />);

    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();

    fetchPeopleMock.mockResolvedValue(samplePeople);
    await user.click(screen.getByRole('button', { name: copy.states.retry }));
    expect(await screen.findByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
  });

  it('shows the people once they arrive', async () => {
    renderWithProviders(<HomePage />);
    expect(await screen.findByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
    expect(shownPeople()).toBe(12);
  });
});

describe('HomePage — an update that fails after the list was shown', () => {
  it('keeps the people on screen and says the update did not work', async () => {
    const { queryClient } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: peopleQueryKey });
    });

    expect(await screen.findByText(copy.states.refreshFailed)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
    expect(screen.queryByText(copy.states.errorBody)).not.toBeInTheDocument();
    expect(shownPeople()).toBe(12);
  });

  it('takes the note away again once an update works', async () => {
    const { queryClient } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    fetchPeopleMock.mockRejectedValueOnce(new DataUnavailableError('people.list'));
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: peopleQueryKey });
    });
    await screen.findByText(copy.states.refreshFailed);

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: peopleQueryKey });
    });
    await waitFor(() => {
      expect(screen.queryByText(copy.states.refreshFailed)).not.toBeInTheDocument();
    });
  });

  it('still shows the full error when there is nothing to show yet', async () => {
    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
    expect(screen.queryByText(copy.states.refreshFailed)).not.toBeInTheDocument();
  });
});

describe('HomePage — a list cut at the cap', () => {
  const cutList = () =>
    Array.from({ length: PEOPLE_MAX_ROWS }, (_, index) => ({
      ...samplePeople[0]!,
      person_id: `p-cut-${String(index)}`,
      waiting_on: 'them' as const,
    }));

  it('warns that the numbers may be too low', async () => {
    fetchPeopleMock.mockResolvedValue(cutList());
    // The filter hides every row: the notice counts the whole list, and drawing
    // thousands of table rows in the test DOM is slow enough to time out on CI.
    renderWithProviders(<HomePage />, { route: '/?waiting=me' });
    await screen.findByText(copy.home.emptyFiltered.title);
    expect(screen.getByText(copy.states.peopleCut(PEOPLE_MAX_ROWS))).toBeInTheDocument();
  });

  it('shows no warning for a list read in full', async () => {
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(screen.queryByText(copy.states.peopleCut(PEOPLE_MAX_ROWS))).not.toBeInTheDocument();
  });
});

describe('HomePage — counters', () => {
  it('prints the hand-counted numbers from the sample data', async () => {
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(counterValue(copy.home.counters.actionsForMe)).toBe('4');
    expect(counterValue(copy.home.counters.overdue)).toBe('2');
    expect(counterValue(copy.home.counters.timeToChase)).toBe('1');
    expect(counterValue(copy.home.counters.waitingOnThem)).toBe('5');
    expect(counterValue(copy.home.counters.activeConversations)).toBe('6');
  });

  it('shows no numbers while the people are still loading', () => {
    fetchPeopleMock.mockReturnValue(new Promise(() => undefined));
    renderWithProviders(<HomePage />);
    expect(screen.getByText(copy.states.loadingPeople)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: copy.home.countersLabel })).not.toBeInTheDocument();
  });

  it('shows no numbers when the people cannot be loaded', async () => {
    fetchPeopleMock.mockRejectedValue(new DataUnavailableError('people.list'));
    renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: copy.home.countersLabel })).not.toBeInTheDocument();
  });

  it('shows real zeros once an empty list has loaded', async () => {
    fetchPeopleMock.mockResolvedValue([]);
    renderWithProviders(<HomePage />);
    await screen.findByText(copy.home.empty.title);
    expect(counterValue(copy.home.counters.actionsForMe)).toBe('0');
  });

  it('keeps describing the whole list even when a filter is on', async () => {
    renderWithProviders(<HomePage />, { route: '/?due=overdue' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(shownPeople()).toBe(2);
    expect(counterValue(copy.home.counters.actionsForMe)).toBe('4');
  });
});

describe('HomePage — counters as filters', () => {
  it.each([
    [copy.home.counters.actionsForMe, '/?waiting=me', 4],
    [copy.home.counters.overdue, '/?due=overdue', 2],
    [copy.home.counters.timeToChase, '/?due=chase', 1],
    [copy.home.counters.waitingOnThem, '/?waiting=them', 5],
    [copy.home.counters.activeConversations, '/?status=active', 6],
  ])('"%s" opens %s and shows %i people', async (label, address, count) => {
    const { user } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    await user.click(counterLink(label));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(address);
    });
    expect(shownPeople()).toBe(count);
    expect(counterLink(label)).toHaveAttribute('aria-current', 'true');
  });

  it('clears the other filters but keeps the order', async () => {
    const { user } = renderWithProviders(<HomePage />, {
      route: '/?type=vc&status=closed&sort=name',
    });
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(shownPeople()).toBe(1);

    await user.click(counterLink(copy.home.counters.overdue));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/?due=overdue&sort=name');
    });
    expect(shownPeople()).toBe(2);
  });

  it('marks no counter while no counter filter is on', async () => {
    renderWithProviders(<HomePage />, { route: '/?type=vc' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    const list = screen.getByRole('list', { name: copy.home.countersLabel });
    for (const link of within(list).getAllByRole('link')) {
      expect(link).not.toHaveAttribute('aria-current');
    }
  });

  it('offers "active" in the status filter', async () => {
    renderWithProviders(<HomePage />, { route: '/?status=active' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(screen.getByLabelText(copy.home.statusFilterLabel)).toHaveValue('active');
    expect(shownPeople()).toBe(6);
  });
});

describe('HomePage — coming up', () => {
  it('lists this week\'s meetings soonest first, each opening its person', async () => {
    fetchMeetingsMock.mockResolvedValue(sampleMeetings);
    renderWithProviders(<HomePage />);

    const strip = await screen.findByRole('region', { name: copy.home.comingUp.title });
    const links = within(strip).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/people/p-01',
      '/people/p-03',
      '/people/p-10',
    ]);
    expect(links[0]).toHaveTextContent('Ana Ruiz');
    expect(links[0]).toHaveTextContent('Northwind Labs');
    expect(links[0]).toHaveTextContent('Coffee with Ana (Northwind)');
    expect(links[2]).toHaveTextContent(copy.home.comingUp.untitled);
  });

  it('asks for the meetings from the frozen "now"', async () => {
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(fetchMeetingsMock).toHaveBeenCalledWith(NOW);
  });

  it('hides itself when nothing is coming up', async () => {
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    const strip = screen.queryByRole('region', { name: copy.home.comingUp.title });
    expect(strip).not.toBeInTheDocument();
  });

  it('shows a meeting with nobody on the list without a link', async () => {
    fetchMeetingsMock.mockResolvedValue([
      { ...sampleMeetings[0]!, person_id: null, people: null },
    ]);
    renderWithProviders(<HomePage />);

    await screen.findByRole('region', { name: copy.home.comingUp.title });
    expect(within(comingUp()).queryByRole('link')).not.toBeInTheDocument();
    expect(within(comingUp()).getByText(copy.home.comingUp.unknownPerson)).toBeInTheDocument();
  });

  it('opens no page for someone not on the list, but still shows the meeting', async () => {
    const [ana, carla, jonas] = sampleMeetings;
    fetchMeetingsMock.mockResolvedValue([
      ana!,
      { ...carla!, people: { ...carla!.people!, relevance: 'unsure' } },
      { ...jonas!, people: { ...jonas!.people!, relevance: 'noise' } },
    ]);
    renderWithProviders(<HomePage />);

    const strip = await screen.findByRole('region', { name: copy.home.comingUp.title });
    const links = within(strip).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/people/p-01']);
    expect(within(strip).getByText('Carla Mendes')).toBeInTheDocument();
    expect(within(strip).getByText('Jonas Berg')).toBeInTheDocument();
  });

  it('says so quietly when the meetings cannot be loaded', async () => {
    fetchMeetingsMock.mockRejectedValue(new DataUnavailableError('meetings.upcoming'));
    renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.home.comingUp.failed)).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
  });
});

describe('HomePage — filters in the address', () => {
  it('puts the chosen type in the address', async () => {
    const { user } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    await user.click(screen.getByRole('button', { name: 'Investors' }));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/?type=vc');
    });
    expect(shownPeople()).toBe(3);
  });

  it('combines the type with the status, waiting-on and due filters', async () => {
    const { user } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    await user.click(screen.getByRole('button', { name: 'Startups' }));
    await user.selectOptions(screen.getByLabelText(copy.home.statusFilterLabel), 'gone_quiet');
    await user.selectOptions(screen.getByLabelText(copy.home.waitingFilterLabel), 'them');
    await user.selectOptions(screen.getByLabelText(copy.home.dueFilterLabel), 'chase');

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/?type=startup&status=gone_quiet&waiting=them&due=chase',
      );
    });
    expect(shownPeople()).toBe(1);
    expect(within(peopleTable()).getByRole('link', { name: 'Kira Novak' })).toBeInTheDocument();
  });

  it('comes back to the same view after a reload of that address', async () => {
    renderWithProviders(<HomePage />, { route: '/?waiting=me&sort=name' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(shownPeople()).toBe(4);
    expect(screen.getByLabelText(copy.home.waitingFilterLabel)).toHaveValue('me');
    expect(screen.getByLabelText(copy.home.sortLabel)).toHaveValue('name');
    expect(screen.getByRole('button', { name: copy.filterLabels.everyone })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('ignores a type the database does not know', async () => {
    renderWithProviders(<HomePage />, { route: '/?type=robot' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(shownPeople()).toBe(12);
    expect(screen.getByRole('button', { name: copy.filterLabels.everyone })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('clears every filter from the empty state', async () => {
    const { user } = renderWithProviders(<HomePage />, {
      route: '/?type=unknown&status=closed&waiting=me&due=overdue&sort=name',
    });

    expect(await screen.findByText(copy.home.emptyFiltered.title)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: copy.home.emptyFiltered.action }));

    expect(await screen.findByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/?sort=name');
    expect(shownPeople()).toBe(12);
  });
});

describe('HomePage — the status grid', () => {
  it('counts every person once, by status and type', async () => {
    renderWithProviders(<HomePage />);
    const grid = await screen.findByRole('table', { name: copy.home.grid.caption });

    const footer = within(grid).getAllByRole('row').at(-1)!;
    expect(within(footer).getByRole('link', { name: /^12:/ })).toBeInTheDocument();
  });

  it('opens exactly the people behind a count', async () => {
    const { user } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.grid.caption });

    const label = copy.home.grid.cellLabel(1, 'Investors', 'In a hiring process');
    await user.click(screen.getByRole('link', { name: label }));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/?type=vc&status=in_process',
      );
    });
    expect(shownPeople()).toBe(1);
    expect(within(peopleTable()).getByRole('link', { name: 'Ines Gallo' })).toBeInTheDocument();
  });
});

/** The names on the type chips, in order. */
function chipNames(): string[] {
  const group = screen.getByRole('group', { name: copy.home.filtersLabel });
  return within(group)
    .getAllByRole('button')
    .map((button) => button.textContent ?? '');
}

/** The status grid's column heads, without the status and total columns. */
function gridColumnNames(): string[] {
  const grid = screen.getByRole('table', { name: copy.home.grid.caption });
  const heads = within(grid).getAllByRole('columnheader');
  return heads.slice(1, -1).map((head) => head.textContent ?? '');
}

describe('HomePage — categories from the database', () => {
  it('shows a five-category profile in the chips, the grid and the badges', async () => {
    fetchCategoriesMock.mockResolvedValue(salesCategories);
    fetchPeopleMock.mockResolvedValue(
      peopleWithCategories(['prospect', 'customer', 'partner', 'referrer']),
    );
    const { user, container } = renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });

    const groups = ['Prospects', 'Customers', 'Partners', 'Referrers', 'Not known'];
    expect(chipNames()).toEqual([copy.filterLabels.everyone, ...groups]);
    expect(gridColumnNames()).toEqual(groups);

    await user.click(screen.getByRole('button', { name: 'Partners' }));
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/?type=partner');
    });
    expect(shownPeople()).toBe(3);
    expect(within(peopleTable()).getAllByText('Partner')).toHaveLength(3);
    await expectNoAxeViolations(container);
  });

  it('works with a single category of its own', async () => {
    fetchCategoriesMock.mockResolvedValue(singleCategory);
    fetchPeopleMock.mockResolvedValue(peopleWithCategories(['member']));
    renderWithProviders(<HomePage />, { route: '/?type=member' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(chipNames()).toEqual([copy.filterLabels.everyone, 'Members', 'Not known']);
    expect(gridColumnNames()).toEqual(['Members', 'Not known']);
    expect(screen.getByRole('button', { name: 'Members' })).toHaveAttribute('aria-pressed', 'true');
    expect(shownPeople()).toBe(12);
  });

  it('keeps an archived category on screen only while someone has it', async () => {
    const archived = withArchived(sampleCategories, 'network');
    fetchCategoriesMock.mockResolvedValue(archived);
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(chipNames()).toContain('Network');
    expect(within(peopleTable()).getAllByText('Network')).toHaveLength(3);
  });

  it('hides an archived category nobody has', async () => {
    const archived = withArchived(sampleCategories, 'network');
    fetchCategoriesMock.mockResolvedValue(archived);
    fetchPeopleMock.mockResolvedValue(
      samplePeople.filter((person) => person.person_type !== 'network'),
    );
    renderWithProviders(<HomePage />, { route: '/?type=network' });
    await screen.findByRole('table', { name: copy.home.tableCaption });

    expect(chipNames()).not.toContain('Network');
    expect(gridColumnNames()).not.toContain('Network');
    expect(shownPeople()).toBe(9);
  });

  it('shows a category key the list does not know as itself', async () => {
    fetchPeopleMock.mockResolvedValue([{ ...samplePeople[0]!, person_type: 'mystery' }]);
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(within(peopleTable()).getByText('mystery')).toBeInTheDocument();
    expect(chipNames()).toContain('mystery');
  });

  it('offers a retry when the categories cannot be loaded', async () => {
    fetchCategoriesMock.mockRejectedValue(new DataUnavailableError('categories.list'));
    const { user } = renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();

    fetchCategoriesMock.mockResolvedValue(sampleCategories);
    await user.click(screen.getByRole('button', { name: copy.states.retry }));
    expect(await screen.findByRole('table', { name: copy.home.tableCaption })).toBeInTheDocument();
  });
});

describe('HomePage — status names from the database', () => {
  /** The status Ines Gallo (an investor in a process) shows in the table. */
  async function inesStatus(): Promise<HTMLElement> {
    await screen.findByRole('table', { name: copy.home.tableCaption });
    const link = within(peopleTable()).getByRole('link', { name: 'Ines Gallo' });
    return link.closest('tr')!;
  }

  it('shows the owner\'s own name for a status', async () => {
    renderWithProviders(<HomePage />);
    expect(within(await inesStatus()).getByText('In a hiring process')).toBeInTheDocument();
  });

  it('falls back to the neutral name for a status with no row', async () => {
    fetchStatusLabelsMock.mockResolvedValue(
      sampleStatusLabels.filter((row) => row.status !== 'in_process'),
    );
    renderWithProviders(<HomePage />);
    const row = await inesStatus();
    expect(within(row).getByText(copy.defaultStatusLabels.in_process)).toBeInTheDocument();
  });

  it('falls back to the neutral names when they cannot be loaded, without an error', async () => {
    fetchStatusLabelsMock.mockRejectedValue(new DataUnavailableError('status_labels.list'));
    renderWithProviders(<HomePage />);
    expect(within(await inesStatus()).getByText('In process')).toBeInTheDocument();
    expect(screen.queryByText(copy.states.errorBody)).not.toBeInTheDocument();
  });
});

describe('HomePage — the run banner', () => {
  it('warns when the newest run failed', async () => {
    renderWithProviders(<HomePage />);
    expect(await screen.findByText(copy.banner.lastRunFailed)).toBeInTheDocument();
  });

  it('says nothing alarming when the last run worked', async () => {
    fetchRunsMock.mockResolvedValue([{ ...sampleRuns[1]!, status: 'success' }]);
    renderWithProviders(<HomePage />);
    await screen.findByRole('table', { name: copy.home.tableCaption });
    expect(screen.queryByText(copy.banner.lastRunFailed)).not.toBeInTheDocument();
  });
});

describe('HomePage — accessibility', () => {
  it('has no axe violations', async () => {
    fetchMeetingsMock.mockResolvedValue(sampleMeetings);
    const { container } = renderWithProviders(<HomePage />, { route: '/?due=overdue' });
    await screen.findByRole('table', { name: copy.home.tableCaption });
    await screen.findByRole('region', { name: copy.home.comingUp.title });
    await expectNoAxeViolations(container);
  });
});
