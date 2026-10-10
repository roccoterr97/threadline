import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as copy from '../copy/en';
import { readSupabaseSource } from '../lib/runtimeConfig';
import { forgetConnection, readSavedConnection, saveConnection } from '../lib/savedConnection';
import { installMemoryStorage } from '../test/memoryStorage';
import { SavedDatabaseNote } from './SavedDatabaseNote';

vi.mock('../lib/runtimeConfig', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/runtimeConfig')>()),
  readSupabaseSource: vi.fn(),
}));

const LINKED = { url: 'https://abcdefghijklmnopqrst.supabase.co', anonKey: 'sb_publishable_x' };

afterEach(() => {
  forgetConnection();
});

describe('SavedDatabaseNote', () => {
  it('names the saved database and forgets it on request', async () => {
    installMemoryStorage();
    saveConnection(LINKED);
    vi.mocked(readSupabaseSource).mockReturnValue({ settings: LINKED, source: 'saved-link' });
    const restart = vi.fn();
    const user = userEvent.setup();
    render(<SavedDatabaseNote restart={restart} />);

    expect(screen.getByText(copy.connect.connectedTo(LINKED.url))).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: copy.connect.forget }));

    expect(readSavedConnection()).toBeNull();
    expect(restart).toHaveBeenCalledOnce();
  });

  it('shows nothing on a dashboard with its own settings', () => {
    vi.mocked(readSupabaseSource).mockReturnValue({ settings: LINKED, source: 'config-file' });
    const { container } = render(<SavedDatabaseNote />);

    expect(container).toBeEmptyDOMElement();
  });
});
