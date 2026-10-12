import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LINKEDIN_GUIDE_URL, LINKEDIN_OFFER_HIDDEN_KEY } from '../constants/links';
import * as copy from '../copy/en';
import { expectNoAxeViolations } from '../test/axe';
import { installMemoryStorage } from '../test/memoryStorage';
import { renderWithProviders } from '../test/renderWithProviders';
import { LinkedInOffer } from './LinkedInOffer';

const text = copy.linkedInOffer;

describe('LinkedInOffer', () => {
  let storage: Storage;

  beforeEach(() => {
    storage = installMemoryStorage();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('offers LinkedIn with the one command and a link to the guide', async () => {
    const { container } = renderWithProviders(<LinkedInOffer />);

    expect(screen.getByRole('heading', { name: text.title })).toBeInTheDocument();
    expect(screen.getByText(text.body)).toBeInTheDocument();
    expect(screen.getByText(text.command)).toBeInTheDocument();
    const guide = screen.getByRole('link', { name: new RegExp(text.guide) });
    expect(guide).toHaveAttribute('href', LINKEDIN_GUIDE_URL);
    expect(guide).toHaveAttribute('target', '_blank');
    await expectNoAxeViolations(container);
  });

  it('goes away when hidden, and stays away on the next visit', async () => {
    const { user, unmount } = renderWithProviders(<LinkedInOffer />);

    await user.click(screen.getByRole('button', { name: text.hideLabel }));

    expect(screen.queryByRole('heading', { name: text.title })).not.toBeInTheDocument();
    expect(storage.getItem(LINKEDIN_OFFER_HIDDEN_KEY)).not.toBeNull();
    unmount();
    renderWithProviders(<LinkedInOffer />);
    expect(screen.queryByRole('heading', { name: text.title })).not.toBeInTheDocument();
  });

  it('still shows, and can still be hidden, when the browser keeps nothing', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { user } = renderWithProviders(<LinkedInOffer />);

    expect(screen.getByRole('heading', { name: text.title })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: text.hideLabel }));
    expect(screen.queryByRole('heading', { name: text.title })).not.toBeInTheDocument();
  });
});
