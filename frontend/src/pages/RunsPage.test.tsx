import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchRecentRuns } from '../api/runs';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { sampleRuns } from '../test/__fixtures__/sampleData';
import { renderWithProviders } from '../test/renderWithProviders';
import { RunsPage } from './RunsPage';

vi.mock('../api/runs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/runs')>()),
  fetchRecentRuns: vi.fn(),
}));

const fetchRunsMock = vi.mocked(fetchRecentRuns);

beforeEach(() => {
  fetchRunsMock.mockResolvedValue(sampleRuns);
});

describe('RunsPage — the four states', () => {
  it('says what it is loading', () => {
    fetchRunsMock.mockReturnValue(new Promise(() => undefined));
    renderWithProviders(<RunsPage />);
    expect(screen.getByText(copy.states.loadingRuns)).toBeInTheDocument();
  });

  it('says so when nothing has run yet', async () => {
    fetchRunsMock.mockResolvedValue([]);
    renderWithProviders(<RunsPage />);
    expect(await screen.findByText(copy.runs.empty.title)).toBeInTheDocument();
  });

  it('offers a retry when the history cannot be loaded', async () => {
    fetchRunsMock.mockRejectedValue(new DataUnavailableError('runs.list'));
    renderWithProviders(<RunsPage />);
    expect(await screen.findByText(copy.states.errorBody)).toBeInTheDocument();
  });

  it('lists the runs with their steps', async () => {
    renderWithProviders(<RunsPage />);
    expect(await screen.findAllByText(copy.runStepLabels.collect_linkedin)).toHaveLength(2);
  });

  it('names the calendar step in plain English', async () => {
    renderWithProviders(<RunsPage />);
    expect(await screen.findByText(copy.runStepLabels.collect_calendar)).toBeInTheDocument();
    expect(screen.queryByText(/collect_calendar/)).not.toBeInTheDocument();
  });
});

describe('RunsPage — plain-English problems', () => {
  it('explains a stored error code in words, never as a code', async () => {
    renderWithProviders(<RunsPage />);
    expect(await screen.findByText(copy.runErrors.source_auth_failed!)).toBeInTheDocument();
    expect(screen.queryByText(/source_auth_failed/)).not.toBeInTheDocument();
  });

  it('never shows the technical detail the run stored', async () => {
    renderWithProviders(<RunsPage />);
    await screen.findByText(copy.runErrors.source_auth_failed!);
    expect(screen.queryByText(/mailbox sign-in was refused/)).not.toBeInTheDocument();
  });

  it('falls back to a general sentence for a code it does not know', async () => {
    const [failedRun] = sampleRuns;
    const unknownCode = {
      ...failedRun!,
      run_step_logs: failedRun!.run_step_logs.map((step) =>
        step.error_code === null ? step : { ...step, error_code: 'something_new' },
      ),
    };
    fetchRunsMock.mockResolvedValue([unknownCode]);

    renderWithProviders(<RunsPage />);
    expect(await screen.findByText(copy.runErrorFallback)).toBeInTheDocument();
  });
});

describe('RunsPage — accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = renderWithProviders(<RunsPage />);
    await screen.findAllByText(copy.runStepLabels.collect_linkedin);
    await expectNoAxeViolations(container);
  });
});
