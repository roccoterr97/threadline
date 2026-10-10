import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { databaseVersionQueryKey, isDatabaseOlder } from '../api/databaseVersion';
import * as copy from '../copy/en';
import { renderWithProviders } from '../test/renderWithProviders';
import { DatabaseUpdateNotice } from './DatabaseUpdateNotice';

vi.mock('../api/databaseVersion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/databaseVersion')>()),
  isDatabaseOlder: vi.fn(),
}));

function renderNotice(older: Promise<boolean>) {
  vi.mocked(isDatabaseOlder).mockReturnValue(older);
  const result = renderWithProviders(<DatabaseUpdateNotice />);
  void result.queryClient.invalidateQueries({ queryKey: databaseVersionQueryKey });
  return result;
}

describe('DatabaseUpdateNotice', () => {
  it('says how to update a database older than the dashboard', async () => {
    renderNotice(Promise.resolve(true));

    expect(await screen.findByRole('status')).toHaveTextContent(copy.databaseUpdate.notice);
  });

  it('shows nothing when the database is up to date', async () => {
    renderNotice(Promise.resolve(false));

    await vi.waitFor(() => {
      expect(isDatabaseOlder).toHaveBeenCalled();
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows nothing when the database cannot be asked', async () => {
    renderNotice(Promise.reject(new Error('down')));

    await vi.waitFor(() => {
      expect(isDatabaseOlder).toHaveBeenCalled();
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
