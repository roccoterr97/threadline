import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import * as copy from '../copy/en';
import { SignInLinkError, SignInRefusal } from '../lib/errors';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/renderWithProviders';
import { LoginPage } from './LoginPage';

const ADDRESS = 'owner@example.test';

function renderLogin(sendSignInLink = vi.fn<(email: string) => Promise<void>>()) {
  sendSignInLink.mockResolvedValue(undefined);
  const result = renderWithProviders(<LoginPage />, {
    route: '/login',
    auth: { status: 'signed-out', email: null, sendSignInLink },
  });
  return { ...result, sendSignInLink };
}

describe('LoginPage', () => {
  it('asks for an email address and nothing else', () => {
    renderLogin();
    expect(screen.getByLabelText(copy.login.emailLabel)).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });

  it('sends the link and says where to look for it', async () => {
    const { user, sendSignInLink } = renderLogin();

    await user.type(screen.getByLabelText(copy.login.emailLabel), ADDRESS);
    await user.click(screen.getByRole('button', { name: copy.login.submit }));

    expect(sendSignInLink).toHaveBeenCalledWith(ADDRESS);
    expect(await screen.findByText(copy.login.sent(ADDRESS))).toBeInTheDocument();
  });

  it('catches a typed address that is not an address', async () => {
    const { user, sendSignInLink } = renderLogin();

    await user.type(screen.getByLabelText(copy.login.emailLabel), 'not-an-address');
    await user.click(screen.getByRole('button', { name: copy.login.submit }));

    expect(await screen.findByText(copy.login.invalidEmail)).toBeInTheDocument();
    expect(sendSignInLink).not.toHaveBeenCalled();
    const field = screen.getByLabelText(copy.login.emailLabel);
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveFocus();
    expect(field).toHaveAccessibleDescription(
      `${copy.login.invalidEmail} ${copy.login.emailHint}`,
    );
  });

  it('tells the owner to try again when the link could not be sent', async () => {
    const failing = vi.fn<(email: string) => Promise<void>>();
    failing.mockRejectedValue(new Error('send failed'));
    const { user } = renderWithProviders(<LoginPage />, {
      route: '/login',
      auth: { status: 'signed-out', email: null, sendSignInLink: failing },
    });

    await user.type(screen.getByLabelText(copy.login.emailLabel), ADDRESS);
    await user.click(screen.getByRole('button', { name: copy.login.submit }));

    expect(await screen.findByText(copy.login.failed)).toBeInTheDocument();
  });

  it.each([
    ['an unknown address', new SignInLinkError(SignInRefusal.UnknownAddress), copy.login.unknownAddress],
    ['a short wait', new SignInLinkError(SignInRefusal.TooManyRequests, 52), copy.login.tooManyLinks(52)],
    ['a long wait', new SignInLinkError(SignInRefusal.TooManyRequests), copy.login.tooManyLinks(null)],
    ['no connection', new SignInLinkError(SignInRefusal.Unavailable), copy.login.failed],
  ])('says what to do next after %s', async (_label, refusal, message) => {
    const failing = vi.fn<(email: string) => Promise<void>>();
    failing.mockRejectedValue(refusal);
    const { user } = renderWithProviders(<LoginPage />, {
      route: '/login',
      auth: { status: 'signed-out', email: null, sendSignInLink: failing },
    });

    await user.type(screen.getByLabelText(copy.login.emailLabel), ADDRESS);
    await user.click(screen.getByRole('button', { name: copy.login.submit }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });

  it('explains itself when the page has no database settings', () => {
    renderWithProviders(<LoginPage />, {
      route: '/login',
      auth: { status: 'not-configured', email: null },
    });
    expect(screen.getByText(copy.states.notConfigured)).toBeInTheDocument();
  });

  it('has no axe violations', async () => {
    const { container } = renderLogin();
    await expectNoAxeViolations(container);
  });
});
