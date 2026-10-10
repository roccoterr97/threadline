import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as copy from '../copy/en';
import { forgetConnection, readSavedConnection } from '../lib/savedConnection';
import { isConfigured } from '../lib/supabaseClient';
import { expectNoAxeViolations } from '../test/axe';
import { installMemoryStorage } from '../test/memoryStorage';
import { ConnectionGate } from './ConnectionGate';

vi.mock('../lib/supabaseClient', () => ({ isConfigured: vi.fn() }));

const LINKED = { url: 'https://abcdefghijklmnopqrst.supabase.co', anonKey: 'sb_publishable_x' };
const OTHER = { url: 'https://zyxwvutsrqponmlkjihg.supabase.co', anonKey: 'sb_publishable_y' };
const DASHBOARD = 'The dashboard';

beforeEach(() => {
  installMemoryStorage();
  // Configured once something is saved, as on the shared dashboard.
  vi.mocked(isConfigured).mockImplementation(() => readSavedConnection() !== null);
});

afterEach(() => {
  forgetConnection();
});

describe('ConnectionGate', () => {
  it('asks for the personal link when the page knows no database', async () => {
    const { container } = render(
      <ConnectionGate startup={{ kind: 'ready' }}>{DASHBOARD}</ConnectionGate>,
    );

    expect(screen.getByRole('heading', { name: copy.connect.title })).toBeInTheDocument();
    expect(screen.getByText(copy.connect.intro)).toBeInTheDocument();
    expect(screen.queryByText(DASHBOARD)).not.toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('opens the dashboard once a whole link is pasted', async () => {
    const user = userEvent.setup();
    render(<ConnectionGate startup={{ kind: 'ready' }}>{DASHBOARD}</ConnectionGate>);

    await user.type(
      screen.getByLabelText(copy.connect.linkLabel),
      `https://app.threadlineapp.com/#project=abcdefghijklmnopqrst&key=sb_publishable_x`,
    );
    await user.click(screen.getByRole('button', { name: copy.connect.submit }));

    expect(screen.getByText(DASHBOARD)).toBeInTheDocument();
    expect(readSavedConnection()).toEqual(LINKED);
  });

  it('says what to do with a pasted link that is not complete', async () => {
    const user = userEvent.setup();
    render(<ConnectionGate startup={{ kind: 'ready' }}>{DASHBOARD}</ConnectionGate>);

    await user.type(screen.getByLabelText(copy.connect.linkLabel), 'https://app.threadlineapp.com/');
    await user.click(screen.getByRole('button', { name: copy.connect.submit }));

    expect(screen.getByRole('alert')).toHaveTextContent(copy.connect.invalidPasted);
    expect(readSavedConnection()).toBeNull();
  });

  it('says so when the page was opened with a broken link', () => {
    render(<ConnectionGate startup={{ kind: 'invalid-link' }}>{DASHBOARD}</ConnectionGate>);

    expect(screen.getByRole('alert')).toHaveTextContent(copy.connect.invalidOpened);
  });

  it('goes straight to the dashboard when the page knows its database', () => {
    vi.mocked(isConfigured).mockReturnValue(true);
    render(<ConnectionGate startup={{ kind: 'ready' }}>{DASHBOARD}</ConnectionGate>);

    expect(screen.getByText(DASHBOARD)).toBeInTheDocument();
  });

  it('switches database only when the owner says so', async () => {
    const user = userEvent.setup();
    vi.mocked(isConfigured).mockReturnValue(true);
    render(
      <ConnectionGate startup={{ kind: 'confirm-switch', current: OTHER, incoming: LINKED }}>
        {DASHBOARD}
      </ConnectionGate>,
    );

    expect(screen.getByText(copy.connect.switchBody(LINKED.url, OTHER.url))).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: copy.connect.switchConfirm }));

    expect(readSavedConnection()).toEqual(LINKED);
    expect(screen.getByText(DASHBOARD)).toBeInTheDocument();
  });

  it('keeps the current database when the owner says so', async () => {
    const user = userEvent.setup();
    vi.mocked(isConfigured).mockReturnValue(true);
    render(
      <ConnectionGate startup={{ kind: 'confirm-switch', current: OTHER, incoming: LINKED }}>
        {DASHBOARD}
      </ConnectionGate>,
    );

    await user.click(screen.getByRole('button', { name: copy.connect.switchKeep }));

    expect(readSavedConnection()).toBeNull();
    expect(screen.getByText(DASHBOARD)).toBeInTheDocument();
  });
});
