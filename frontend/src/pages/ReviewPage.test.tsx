import { screen, waitFor, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { upcomingMeetingsQueryKey } from '../api/meetings';
import { fetchPeople } from '../api/people';
import { answerReviewItem, fetchOpenReviewItems } from '../api/review';
import { AppLayout } from '../components/AppLayout';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { NOW, samplePeople, sampleReviewItems } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { scrollIntoViewCalls } from '../test/scrollIntoView';
import { ReviewPage } from './ReviewPage';

vi.mock('../api/review', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/review')>()),
  fetchOpenReviewItems: vi.fn(),
  answerReviewItem: vi.fn(),
}));

vi.mock('../api/people', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/people')>()),
  fetchPeople: vi.fn(),
}));

const fetchItemsMock = vi.mocked(fetchOpenReviewItems);
const fetchPeopleMock = vi.mocked(fetchPeople);
const answerMock = vi.mocked(answerReviewItem);

const [FIRST_ITEM, SECOND_ITEM] = sampleReviewItems;

beforeEach(() => {
  fetchPeopleMock.mockResolvedValue(samplePeople);
  fetchItemsMock.mockResolvedValue(sampleReviewItems);
  answerMock.mockResolvedValue(undefined);
});

describe('ReviewPage — the four states', () => {
  it('says what it is loading', () => {
    fetchItemsMock.mockReturnValue(new Promise(() => undefined));
    renderWithProviders(<ReviewPage />);
    expect(screen.getByText(copy.states.loadingReview)).toBeInTheDocument();
  });

  it('says so when there is nothing to review', async () => {
    fetchItemsMock.mockResolvedValue([]);
    renderWithProviders(<ReviewPage />);
    expect(await screen.findByText(copy.review.empty.title)).toBeInTheDocument();
  });

  it('offers a retry when the questions cannot be loaded', async () => {
    fetchItemsMock.mockRejectedValue(new DataUnavailableError('review.list'));
    renderWithProviders(<ReviewPage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
  });

  it('shows one card per open question', async () => {
    renderWithProviders(<ReviewPage />);
    expect(await screen.findAllByRole('listitem')).toHaveLength(2);
  });
});

describe('ReviewPage — answering', () => {
  it('stores the answer with the moment it was given and drops the card', async () => {
    fetchItemsMock.mockResolvedValueOnce(sampleReviewItems);
    fetchItemsMock.mockResolvedValue([SECOND_ITEM!]);

    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));

    await waitFor(() => {
      expect(answerMock).toHaveBeenCalledWith(FIRST_ITEM!.id, 'yes', NOW);
    });
    await waitFor(() => {
      expect(screen.queryByText(FIRST_ITEM!.question)).not.toBeInTheDocument();
    });
    expect(screen.getByText(SECOND_ITEM!.question)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(copy.review.answered.relevance.yes);
    });
  });

  it('gives the keyboard to the next question and only reads the saved answer out', async () => {
    fetchItemsMock.mockResolvedValueOnce(sampleReviewItems);
    fetchItemsMock.mockResolvedValue([SECOND_ITEM!]);
    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));

    const status = screen.getByRole('status');
    await waitFor(() => {
      expect(status).toHaveTextContent(copy.review.answered.relevance.yes);
    });
    expect(screen.getByText(SECOND_ITEM!.question)).toHaveFocus();
    expect(scrollIntoViewCalls(status)).toEqual([]);
  });

  it('gives the keyboard to the question before when the last one is answered', async () => {
    const { user } = renderWithProviders(<ReviewPage />);
    const secondCard = (await screen.findAllByRole('listitem'))[1]!;

    await user.click(within(secondCard).getByRole('button', { name: copy.review.no }));

    await waitFor(() => {
      expect(screen.getByText(FIRST_ITEM!.question)).toHaveFocus();
    });
  });

  it('gives the keyboard to the note that nothing is left after the last question', async () => {
    fetchItemsMock.mockResolvedValueOnce([FIRST_ITEM!]);
    fetchItemsMock.mockResolvedValue([]);
    const { user } = renderWithProviders(<ReviewPage />);
    const card = await screen.findByRole('listitem');

    await user.click(within(card).getByRole('button', { name: copy.review.yes }));

    await waitFor(() => {
      expect(document.activeElement).toHaveTextContent(copy.review.empty.title);
    });
  });

  it('says what happens next after each kind of answer', async () => {
    const { user } = renderWithProviders(<ReviewPage />);
    const secondCard = (await screen.findAllByRole('listitem'))[1]!;
    await user.click(within(secondCard).getByRole('button', { name: copy.review.no }));

    expect(await screen.findByText(copy.review.answered.same_person.no)).toBeInTheDocument();
  });

  it('styles neither answer as the expected one and ties each to its question', async () => {
    renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;
    const yes = within(firstCard).getByRole('button', { name: copy.review.yes });
    const no = within(firstCard).getByRole('button', { name: copy.review.no });

    expect(yes).toHaveAccessibleDescription(FIRST_ITEM!.question);
    expect(no).toHaveAccessibleDescription(FIRST_ITEM!.question);
    expect(yes.className).toBe(no.className);
  });

  it('links each question to the people it names who are on the list', async () => {
    fetchPeopleMock.mockResolvedValue(samplePeople.filter((p) => p.person_id !== 'p-09'));
    renderWithProviders(<ReviewPage />);
    const [first, second] = await screen.findAllByRole('listitem');

    expect(
      await within(first!).findByRole('link', { name: copy.home.openPerson('Hugo Prieto') }),
    ).toHaveAttribute('href', '/people/p-08');
    expect(within(second!).getAllByRole('link')).toHaveLength(1);
    expect(
      within(second!).getByRole('link', { name: copy.home.openPerson('Carla Mendes') }),
    ).toHaveAttribute('href', '/people/p-03');
  });

  it('sends "no" when the owner says no', async () => {
    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.no }));

    await waitFor(() => {
      expect(answerMock).toHaveBeenCalledWith(FIRST_ITEM!.id, 'no', NOW);
    });
  });

  it('refreshes the meetings strip, since an answer can put someone on the list or take them off', async () => {
    const { user, queryClient } = renderWithProviders(<ReviewPage />);
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;
    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));

    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: upcomingMeetingsQueryKey });
    });
  });

  it('puts the card back and explains itself when saving fails', async () => {
    answerMock.mockRejectedValue(new DataUnavailableError('review.answer'));
    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));

    expect(await screen.findByText(copy.review.failed)).toBeInTheDocument();
    expect(screen.getByText(FIRST_ITEM!.question)).toBeInTheDocument();
  });

  it('gives the keyboard to a failed answer\'s message on its card', async () => {
    answerMock.mockRejectedValue(new DataUnavailableError('review.answer'));
    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(copy.review.failed);
    expect(alert.closest('li')).toHaveTextContent(FIRST_ITEM!.question);
    expect(alert).toHaveFocus();
    expect(scrollIntoViewCalls(alert)).toHaveLength(1);
  });
});

describe('ReviewPage — the count in the navigation', () => {
  it('drops by one when a question is answered', async () => {
    fetchItemsMock.mockResolvedValueOnce(sampleReviewItems);
    fetchItemsMock.mockResolvedValue([SECOND_ITEM!]);

    const { user } = renderWithProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/review" element={<ReviewPage />} />
        </Route>
      </Routes>,
      { route: '/review', path: null },
    );

    const menu = within(screen.getByRole('navigation', { name: copy.nav.headerLabel }));
    const reviewLink = await menu.findByRole('link', { name: /To review/ });
    await waitFor(() => {
      expect(reviewLink).toHaveTextContent(copy.nav.reviewCountLabel(2));
    });

    const cards = await within(screen.getByRole('main')).findAllByRole('listitem');
    await user.click(within(cards[0]!).getByRole('button', { name: copy.review.yes }));

    await waitFor(() => {
      expect(reviewLink).toHaveTextContent(copy.nav.reviewCountLabel(1));
    });
  });
});

describe('ReviewPage — two answers at once', () => {
  /**
   * The first answer hangs until `failFirst` is called; the second one is
   * stored at once, so the database stops returning that question.
   */
  function firstAnswerFailsLate() {
    let open = [...sampleReviewItems];
    let failFirst: () => void = () => undefined;
    fetchItemsMock.mockImplementation(() => Promise.resolve(open));
    answerMock.mockImplementation((itemId) => {
      if (itemId === FIRST_ITEM!.id) {
        return new Promise<void>((_resolve, reject) => {
          failFirst = () => {
            reject(new DataUnavailableError('review.answer'));
          };
        });
      }
      open = open.filter((item) => item.id !== itemId);
      return Promise.resolve();
    });
    return { failFirst: () => failFirst() };
  }

  it('brings back only the failed card, not one answered in the meantime', async () => {
    const { failFirst } = firstAnswerFailsLate();
    const { user, queryClient } = renderWithProviders(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/review" element={<ReviewPage />} />
        </Route>
      </Routes>,
      { route: '/review', path: null },
    );
    const main = within(screen.getByRole('main'));
    const menu = within(screen.getByRole('navigation', { name: copy.nav.headerLabel }));
    const reviewLink = await menu.findByRole('link', { name: /To review/ });

    const firstCard = (await main.findAllByRole('listitem'))[0]!;
    await user.click(within(firstCard).getByRole('button', { name: copy.review.yes }));
    const secondCard = await main.findByRole('listitem');
    expect(secondCard).toHaveTextContent(SECOND_ITEM!.question);
    await user.click(within(secondCard).getByRole('button', { name: copy.review.yes }));

    // Once the second answer is stored, only the first is still on its way.
    await waitFor(() => {
      expect(queryClient.isMutating()).toBe(1);
    });
    await waitFor(() => {
      expect(queryClient.isFetching()).toBe(0);
    });
    // Refreshing after the second answer must not pull back the first card
    // while its answer is still on the way.
    expect(main.queryAllByRole('listitem')).toHaveLength(0);

    failFirst();

    expect(await main.findByText(copy.review.failed)).toBeInTheDocument();
    expect(main.getByText(FIRST_ITEM!.question)).toBeInTheDocument();
    expect(main.queryByText(SECOND_ITEM!.question)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(reviewLink).toHaveTextContent(copy.nav.reviewCountLabel(1));
    });
  });
});

describe('ReviewPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderWithProviders(<ReviewPage />);
    await screen.findAllByRole('listitem');
    await expectNoAxeViolations(container);
  });
});
