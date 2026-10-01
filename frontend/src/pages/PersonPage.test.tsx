import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCategories } from '../api/categories';
import { clearOverride, fetchOverride, markPersonAsNoise, saveOverride } from '../api/overrides';
import { fetchPerson, fetchPersonConversations } from '../api/person';
import { fetchStatusLabels } from '../api/statusLabels';
import * as copy from '../copy/en';
import { DataUnavailableError, NotSignedInError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import {
  sampleCategories,
  sampleConversations,
  sampleOverride,
  samplePerson,
  sampleStatusLabels,
  withArchived,
} from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { PersonPage } from './PersonPage';

vi.mock('../api/person', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/person')>()),
  fetchPerson: vi.fn(),
  fetchPersonConversations: vi.fn(),
}));

vi.mock('../api/overrides', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/overrides')>()),
  fetchOverride: vi.fn(),
  saveOverride: vi.fn(),
  clearOverride: vi.fn(),
  markPersonAsNoise: vi.fn(),
}));

vi.mock('../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categories')>()),
  fetchCategories: vi.fn(),
}));

vi.mock('../api/statusLabels', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/statusLabels')>()),
  fetchStatusLabels: vi.fn(),
}));

const fetchPersonMock = vi.mocked(fetchPerson);
const fetchCategoriesMock = vi.mocked(fetchCategories);
const fetchStatusLabelsMock = vi.mocked(fetchStatusLabels);
const fetchConversationsMock = vi.mocked(fetchPersonConversations);
const fetchOverrideMock = vi.mocked(fetchOverride);
const saveOverrideMock = vi.mocked(saveOverride);
const clearOverrideMock = vi.mocked(clearOverride);
const markNoiseMock = vi.mocked(markPersonAsNoise);

const PERSON = samplePerson('p-01');

function renderPerson(personId = PERSON.person_id) {
  return renderWithProviders(<PersonPage />, {
    route: `/people/${personId}`,
    path: '/people/:personId',
  });
}

/** Waits for the page, then unfolds "Correct this". */
async function openCorrection(user: ReturnType<typeof renderPerson>['user']) {
  await screen.findByRole('heading', { level: 1, name: PERSON.full_name });
  await user.click(screen.getByText(copy.override.title));
}

/** The badges under the person's name, away from the form's options. */
function currentState() {
  return within(screen.getByRole('group', { name: copy.person.stateGroupLabel }));
}

beforeEach(() => {
  fetchPersonMock.mockResolvedValue(PERSON);
  fetchConversationsMock.mockResolvedValue(sampleConversations);
  fetchOverrideMock.mockResolvedValue(null);
  saveOverrideMock.mockResolvedValue(undefined);
  clearOverrideMock.mockResolvedValue(undefined);
  markNoiseMock.mockResolvedValue(undefined);
  fetchCategoriesMock.mockResolvedValue(sampleCategories);
  fetchStatusLabelsMock.mockResolvedValue(sampleStatusLabels);
});

describe('PersonPage — the four states', () => {
  it('says what it is loading', () => {
    fetchPersonMock.mockReturnValue(new Promise(() => undefined));
    renderPerson();
    expect(screen.getByText(copy.states.loadingPerson)).toBeInTheDocument();
  });

  it('explains a person who is not there', async () => {
    fetchPersonMock.mockResolvedValue(null);
    renderPerson('missing');
    expect(await screen.findByText(copy.person.notFound.title)).toBeInTheDocument();
  });

  it('offers a retry when the person cannot be loaded', async () => {
    fetchPersonMock.mockRejectedValue(new DataUnavailableError('person.get'));
    renderPerson();
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: copy.states.retry })).toBeInTheDocument();
  });

  it('shows an empty timeline rather than a blank space', async () => {
    fetchConversationsMock.mockResolvedValue([]);
    renderPerson();
    expect(await screen.findByText(copy.person.timelineEmpty)).toBeInTheDocument();
  });
});

describe('PersonPage — timeline', () => {
  it('mixes every channel into one list, newest first', async () => {
    renderPerson();
    const messages = await screen.findAllByRole('listitem');
    const texts = messages.map((item) => item.textContent ?? '');
    expect(texts[0]).toContain('Does Friday morning suit you?');
    expect(texts.some((text) => text.includes(copy.channelLabels.email))).toBe(true);
    expect(texts.some((text) => text.includes(copy.channelLabels.linkedin))).toBe(true);
  });

  it('shows a calendar meeting with its label and title', async () => {
    renderPerson();
    const messages = await screen.findAllByRole('listitem');
    const meeting = messages.find((item) =>
      item.textContent?.includes('Coffee with Ana (Northwind)'),
    );
    expect(meeting).toBeDefined();
    expect(within(meeting!).getByText(copy.channelLabels.calendar)).toBeInTheDocument();
  });
});

describe('PersonPage — layout', () => {
  it('puts the history before the correction form', async () => {
    renderPerson();
    const history = await screen.findByRole('heading', { level: 2, name: copy.person.timelineTitle });
    const correction = screen.getByText(copy.override.title);
    expect(history.compareDocumentPosition(correction)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('keeps the correction form folded until it is opened', async () => {
    const { user } = renderPerson();
    const statusField = await screen.findByLabelText(copy.override.statusLabel);
    expect(statusField).not.toBeVisible();

    await user.click(screen.getByText(copy.override.title));
    expect(statusField).toBeVisible();

    await user.click(screen.getByText(copy.override.title));
    expect(statusField).not.toBeVisible();
  });

  it('keeps the save result on screen when the form is folded again', async () => {
    const { user } = renderPerson();
    await openCorrection(user);
    await user.click(screen.getByRole('button', { name: copy.override.save }));
    await user.click(screen.getByText(copy.override.title));

    const banner = await screen.findByRole('status');
    expect(banner).toHaveTextContent(copy.override.saved);
    expect(banner).toBeVisible();
  });
});

const LONG_OPENING = 'Thanks for the call today.';
const LONG_ENDING = 'Best wishes, Ana';
const LONG_BODY = [LONG_OPENING, 'Line two', 'Line three', 'Line four', 'Line five', 'Line six', 'Line seven', LONG_ENDING].join('\n');

function withOneMessage(body: string) {
  const [first] = sampleConversations;
  return [{ ...first!, messages: [{ ...first!.messages[0]!, body }] }];
}

describe('PersonPage — long messages', () => {
  it('shows short messages whole, with nothing to unfold', async () => {
    renderPerson();
    await screen.findAllByRole('listitem');
    expect(screen.queryByRole('button', { name: copy.person.showMore })).not.toBeInTheDocument();
  });

  it('folds a long message and unfolds it on request', async () => {
    fetchConversationsMock.mockResolvedValue(withOneMessage(LONG_BODY));
    const { user } = renderPerson();

    const toggle = await screen.findByRole('button', { name: copy.person.showMore });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText(new RegExp(LONG_OPENING))).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(LONG_ENDING))).not.toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent(copy.person.showLess);
    expect(screen.getByText(new RegExp(LONG_ENDING))).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.queryByText(new RegExp(LONG_ENDING))).not.toBeInTheDocument();
  });
});

describe('PersonPage — corrections', () => {
  it('shows the new status at once and keeps it when the save works', async () => {
    const { user } = renderPerson();
    await openCorrection(user);

    await user.selectOptions(
      screen.getByLabelText(copy.override.statusLabel),
      'meeting_planned',
    );
    await user.click(screen.getByRole('button', { name: copy.override.save }));

    const banner = await screen.findByRole('status');
    expect(banner).toHaveTextContent(copy.override.saved);
    expect(banner).toHaveFocus();
    expect(saveOverrideMock).toHaveBeenCalledWith(
      expect.objectContaining({ person_id: PERSON.person_id, status: 'meeting_planned' }),
    );
  });

  it('says so plainly when the save was refused because the sign-in ran out', async () => {
    saveOverrideMock.mockRejectedValue(new NotSignedInError('override.save'));

    const { user } = renderPerson();
    await openCorrection(user);
    await user.click(screen.getByRole('button', { name: copy.override.save }));

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent(copy.override.failedSignedOut);
    expect(banner).toHaveFocus();
  });

  it('puts the old status back and explains itself when the save fails', async () => {
    let rejectSave: (error: Error) => void = () => undefined;
    saveOverrideMock.mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectSave = reject;
        }),
    );

    const { user } = renderPerson();
    await openCorrection(user);
    expect(currentState().getByText('In conversation')).toBeInTheDocument();

    await user.selectOptions(
      screen.getByLabelText(copy.override.statusLabel),
      'meeting_planned',
    );
    await user.click(screen.getByRole('button', { name: copy.override.save }));

    // The screen shows the correction before the database has confirmed it.
    await waitFor(() => {
      expect(currentState().getByText('Meeting planned')).toBeInTheDocument();
    });

    rejectSave(new DataUnavailableError('override.save'));

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.override.failed);
    await waitFor(() => {
      expect(currentState().getByText('In conversation')).toBeInTheDocument();
    });
  });

  it('shows nothing while a save is still waiting for the database', async () => {
    saveOverrideMock.mockReturnValue(new Promise(() => undefined));

    const { user } = renderPerson();
    await openCorrection(user);
    await user.click(screen.getByRole('button', { name: copy.override.save }));

    expect(
      await screen.findByRole('button', { name: copy.override.saving }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not keep saying "saved" when a later clear fails', async () => {
    fetchOverrideMock.mockResolvedValue(sampleOverride);
    clearOverrideMock.mockRejectedValue(new DataUnavailableError('override.clear'));

    const { user } = renderPerson();
    await openCorrection(user);
    await user.click(await screen.findByRole('button', { name: copy.override.save }));
    expect(await screen.findByRole('status')).toHaveTextContent(copy.override.saved);

    await user.click(screen.getByRole('button', { name: copy.override.clear }));

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.override.clearFailed);
    expect(screen.queryByText(copy.override.saved)).not.toBeInTheDocument();
  });

  it('offers "clear my correction" only when there is one', async () => {
    const { user } = renderPerson();
    await openCorrection(user);
    expect(screen.queryByRole('button', { name: copy.override.clear })).not.toBeInTheDocument();
  });

  it('clears a correction and says so', async () => {
    fetchOverrideMock.mockResolvedValue(sampleOverride);
    const { user } = renderPerson();
    await openCorrection(user);

    await user.click(await screen.findByRole('button', { name: copy.override.clear }));

    expect(await screen.findByText(copy.override.cleared)).toBeInTheDocument();
    expect(clearOverrideMock).toHaveBeenCalledWith(PERSON.person_id);
  });
});

describe('PersonPage — categories', () => {
  const archived = withArchived(sampleCategories, 'network');

  it('shows the person\'s category by its name from the database', async () => {
    renderPerson();
    await screen.findByRole('heading', { level: 1, name: PERSON.full_name });
    expect(currentState().getByText('Startup')).toBeInTheDocument();
  });

  it('still names a person\'s archived category', async () => {
    fetchCategoriesMock.mockResolvedValue(archived);
    fetchPersonMock.mockResolvedValue({ ...PERSON, person_type: 'network' });
    renderPerson();
    await screen.findByRole('heading', { level: 1, name: PERSON.full_name });
    expect(currentState().getByText('Network')).toBeInTheDocument();
  });

  it('does not offer an archived category as a correction', async () => {
    fetchCategoriesMock.mockResolvedValue(archived);
    const { user } = renderPerson();
    await openCorrection(user);

    const field = await screen.findByLabelText(copy.override.personTypeLabel);
    const options = within(field).getAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual([copy.override.keepAssistantValue, 'Startup', 'Investor', 'Not known']);
  });

  it('keeps a saved correction to a since-archived category on the form', async () => {
    fetchCategoriesMock.mockResolvedValue(archived);
    fetchOverrideMock.mockResolvedValue(sampleOverride);
    const { user } = renderPerson();
    await openCorrection(user);

    expect(await screen.findByLabelText(copy.override.personTypeLabel)).toHaveValue('network');
  });

  it('offers a retry when the categories cannot be loaded', async () => {
    fetchCategoriesMock.mockRejectedValue(new DataUnavailableError('categories.list'));
    renderPerson();
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
  });
});

describe('PersonPage — not relevant', () => {
  it('asks before hiding a person', async () => {
    const { user } = renderPerson();
    await user.click(await screen.findByRole('button', { name: copy.person.markNoise.button }));

    expect(screen.getByText(copy.person.markNoise.confirmTitle)).toBeInTheDocument();
    expect(markNoiseMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: copy.person.markNoise.confirm }));
    await waitFor(() => {
      expect(markNoiseMock).toHaveBeenCalledWith(PERSON.person_id);
    });
  });

  it('can be backed out of', async () => {
    const { user } = renderPerson();
    await user.click(await screen.findByRole('button', { name: copy.person.markNoise.button }));
    await user.click(screen.getByRole('button', { name: copy.person.markNoise.cancel }));

    expect(screen.queryByText(copy.person.markNoise.confirmTitle)).not.toBeInTheDocument();
    expect(markNoiseMock).not.toHaveBeenCalled();
  });
});

describe('PersonPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderPerson();
    await screen.findByRole('heading', { level: 1, name: PERSON.full_name });
    await expectNoAxeViolations(container);
  });

  it('has no axe violations with the form open and a long message unfolded', async () => {
    fetchConversationsMock.mockResolvedValue(withOneMessage(LONG_BODY));
    const { container, user } = renderPerson();
    await openCorrection(user);
    await user.click(await screen.findByRole('button', { name: copy.person.showMore }));
    await expectNoAxeViolations(container);
  });
});
