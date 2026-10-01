import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchRunSince, requestRefresh } from '../api/refresh';
import { fetchOpenReviewItems } from '../api/review';
import * as copy from '../copy/en';
import { expectNoAxeViolations } from '../test/axe';
import { NOW, sampleReviewItems } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { AppLayout } from './AppLayout';

vi.mock('../api/review', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/review')>()),
  fetchOpenReviewItems: vi.fn(),
}));

vi.mock('../api/refresh', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/refresh')>()),
  requestRefresh: vi.fn(),
  fetchRunSince: vi.fn(),
}));

const fetchItemsMock = vi.mocked(fetchOpenReviewItems);
const requestRefreshMock = vi.mocked(requestRefresh);
const fetchRunSinceMock = vi.mocked(fetchRunSince);
const REVIEW_COUNT_TEXT = copy.nav.reviewCountLabel(sampleReviewItems.length);

function renderLayout(route: string, signOut = vi.fn(() => Promise.resolve())) {
  const result = renderWithProviders(
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<p>People page</p>} />
        <Route path="/review" element={<p>Review page</p>} />
        <Route path="/runs" element={<p>Runs page</p>} />
      </Route>
    </Routes>,
    { route, path: null, auth: { signOut } },
  );
  return { ...result, signOut };
}

function bottomBar() {
  return within(screen.getByRole('navigation', { name: copy.nav.bottomBarLabel }));
}

beforeEach(() => {
  fetchItemsMock.mockResolvedValue(sampleReviewItems);
  fetchRunSinceMock.mockResolvedValue(null);
});

describe('AppLayout — phone bottom bar', () => {
  it('lists every page and marks the current one', async () => {
    renderLayout('/runs');
    const current = bottomBar().getByRole('link', { name: copy.nav.runs });
    expect(current).toHaveAttribute('aria-current', 'page');

    const people = bottomBar().getByRole('link', { name: copy.nav.home });
    expect(people).not.toHaveAttribute('aria-current');
    expect(people).toHaveAttribute('href', '/');
    expect(await screen.findByText('Runs page')).toBeInTheDocument();
  });

  it('shows how many questions are waiting on the review link', async () => {
    renderLayout('/');
    const review = await bottomBar().findByRole('link', {
      name: `${copy.nav.review} ${REVIEW_COUNT_TEXT}`,
    });
    expect(review).toHaveAttribute('href', '/review');
    expect(within(review).getByText(String(sampleReviewItems.length))).toBeInTheDocument();
  });

  it('shows no count when there is nothing to review', async () => {
    fetchItemsMock.mockResolvedValue([]);
    renderLayout('/');
    await screen.findByText('People page');
    expect(bottomBar().getByRole('link', { name: copy.nav.review })).toBeInTheDocument();
  });

  it('moves to another page when a link is tapped', async () => {
    const { user } = renderLayout('/');
    await user.click(bottomBar().getByRole('link', { name: copy.nav.runs }));
    expect(screen.getByTestId('location')).toHaveTextContent('/runs');
    expect(bottomBar().getByRole('link', { name: copy.nav.runs })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});

describe('AppLayout — header', () => {
  it('names the app and keeps the same menu for larger screens', async () => {
    renderLayout('/review');
    expect(screen.getByRole('link', { name: copy.app.name })).toHaveAttribute('href', '/');
    const header = within(screen.getByRole('navigation', { name: copy.nav.headerLabel }));
    expect(
      await header.findByRole('link', { name: `${copy.nav.review} ${REVIEW_COUNT_TEXT}` }),
    ).toHaveAttribute('aria-current', 'page');
  });

  it('signs out', async () => {
    const { user, signOut } = renderLayout('/');
    await user.click(screen.getByRole('button', { name: copy.nav.signOut }));
    expect(signOut).toHaveBeenCalledOnce();
  });

  it('has no axe violations', async () => {
    const { container } = renderLayout('/review');
    await screen.findByText('Review page');
    await expectNoAxeViolations(container);
  });
});

describe('AppLayout — Refresh now', () => {
  const refreshButton = () => screen.getByRole('button', { name: copy.refresh.button });

  it('starts a refresh and says new messages are on their way', async () => {
    requestRefreshMock.mockResolvedValue({ kind: 'started', requestedAt: NOW, target: 'github' });
    const { user } = renderLayout('/');
    await user.click(refreshButton());
    expect(await screen.findByRole('status')).toHaveTextContent(copy.refresh.waiting);
    expect(screen.getByRole('button', { name: copy.refresh.busy })).toBeDisabled();
    expect(fetchRunSinceMock).toHaveBeenCalledWith(NOW);
  });

  it('shows the result once the run has finished', async () => {
    requestRefreshMock.mockResolvedValue({ kind: 'started', requestedAt: NOW, target: 'github' });
    fetchRunSinceMock.mockResolvedValue(finishedRun('partial'));
    const { user } = renderLayout('/');
    await user.click(refreshButton());
    const status = await screen.findByText(copy.refresh.finished.partial);
    expect(status).toBeInTheDocument();
    expect(screen.getByRole('link', { name: copy.refresh.seeRuns })).toHaveAttribute('href', '/runs');
    expect(refreshButton()).toBeEnabled();
  });

  it('explains a refusal in plain words', async () => {
    requestRefreshMock.mockResolvedValue({
      kind: 'refused',
      code: 'too_soon',
      target: 'github',
      retryAfterSeconds: 240,
    });
    const { user } = renderLayout('/');
    await user.click(refreshButton());
    expect(await screen.findByRole('status')).toHaveTextContent('in 4 minutes');
  });

  it('tries again on the next click after the service was not deployed', async () => {
    requestRefreshMock.mockResolvedValueOnce({
      kind: 'refused',
      code: 'not_deployed',
      target: null,
      retryAfterSeconds: null,
    });
    requestRefreshMock.mockResolvedValueOnce({ kind: 'started', requestedAt: NOW, target: 'github' });
    const { user, unmount } = renderLayout('/');
    await user.click(refreshButton());
    expect(await screen.findByRole('status')).toHaveTextContent(copy.refresh.refusals.not_deployed());
    expect(refreshButton()).toBeEnabled();

    await user.click(refreshButton());
    expect(await screen.findByRole('status')).toHaveTextContent(copy.refresh.waiting);
    expect(requestRefreshMock).toHaveBeenCalledTimes(2);

    unmount();
    renderLayout('/');
    expect(refreshButton()).toBeEnabled();
  });

  it('shows "sending" while a click waits for an answer', async () => {
    requestRefreshMock.mockReturnValue(new Promise(() => undefined));
    const { user } = renderLayout('/');
    await user.click(refreshButton());
    expect(await screen.findByRole('status')).toHaveTextContent(copy.refresh.sending);
  });

  it('has no axe violations while refreshing', async () => {
    requestRefreshMock.mockResolvedValue({ kind: 'started', requestedAt: NOW, target: 'github' });
    const { user, container } = renderLayout('/');
    await user.click(refreshButton());
    await screen.findByText(copy.refresh.waiting);
    await expectNoAxeViolations(container);
  });
});

function finishedRun(status: 'success' | 'partial' | 'failed') {
  const stamp = NOW.toISOString();
  return {
    id: 'run-refresh',
    created_at: stamp,
    updated_at: stamp,
    started_at: stamp,
    finished_at: stamp,
    status,
    trigger: 'refresh',
  };
}
