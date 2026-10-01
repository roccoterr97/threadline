import { screen, waitFor, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { answerReviewItem, fetchOpenReviewItems } from '../api/review';
import { AppLayout } from '../components/AppLayout';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { NOW, sampleReviewItems } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { ReviewPage } from './ReviewPage';

vi.mock('../api/review', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/review')>()),
  fetchOpenReviewItems: vi.fn(),
  answerReviewItem: vi.fn(),
}));

const fetchItemsMock = vi.mocked(fetchOpenReviewItems);
const answerMock = vi.mocked(answerReviewItem);

const [FIRST_ITEM, SECOND_ITEM] = sampleReviewItems;

beforeEach(() => {
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
  });

  it('sends "no" when the owner says no', async () => {
    const { user } = renderWithProviders(<ReviewPage />);
    const firstCard = (await screen.findAllByRole('listitem'))[0]!;

    await user.click(within(firstCard).getByRole('button', { name: copy.review.no }));

    await waitFor(() => {
      expect(answerMock).toHaveBeenCalledWith(FIRST_ITEM!.id, 'no', NOW);
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

describe('ReviewPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderWithProviders(<ReviewPage />);
    await screen.findAllByRole('listitem');
    await expectNoAxeViolations(container);
  });
});
