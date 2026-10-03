import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { markPersonAsRelevant } from '../api/overrides';
import * as copy from '../copy/en';
import { DataUnavailableError } from '../lib/errors';
import { hiddenPersonState } from '../lib/hiddenPerson';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/renderWithProviders';
import { scrollIntoViewCalls } from '../test/scrollIntoView';
import { HiddenPersonNotice } from './HiddenPersonNotice';

vi.mock('../api/overrides', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/overrides')>()),
  markPersonAsRelevant: vi.fn(),
}));

const restoreMock = vi.mocked(markPersonAsRelevant);
const ADA = { id: 'p-01', name: 'Ada Lovelace' };
const text = copy.person.hidden;

function renderNotice(state: unknown = hiddenPersonState(ADA)) {
  return renderWithProviders(<HiddenPersonNotice />, { route: '/?type=startup', state });
}

beforeEach(() => {
  restoreMock.mockResolvedValue(undefined);
});

describe('HiddenPersonNotice', () => {
  it('says who was hidden and takes focus', async () => {
    const { container } = renderNotice();
    const note = screen.getByRole('status');
    expect(note).toHaveTextContent(text.notice(ADA.name));
    expect(note).toHaveFocus();
    await expectNoAxeViolations(container);
  });

  it('shows nothing on a normal visit', () => {
    renderNotice(null);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('keeps the filters in the address while it clears the note from history', () => {
    renderNotice();
    expect(screen.getByTestId('location')).toHaveTextContent('/?type=startup');
  });

  it('puts the person back on the list when asked', async () => {
    const { user } = renderNotice();
    await user.click(screen.getByRole('button', { name: text.undoLabel(ADA.name) }));

    expect(await screen.findByText(text.restored(ADA.name))).toBeInTheDocument();
    expect(restoreMock).toHaveBeenCalledWith(ADA.id);
    expect(screen.queryByRole('button', { name: text.undoLabel(ADA.name) })).not.toBeInTheDocument();
  });

  it('keeps the keyboard on the note once "Undo" has gone', async () => {
    let finishUndo = () => undefined;
    restoreMock.mockReturnValue(
      new Promise((resolve) => {
        finishUndo = () => {
          resolve(undefined);
        };
      }),
    );
    const { user } = renderNotice();
    const undo = screen.getByRole('button', { name: text.undoLabel(ADA.name) });
    await user.click(undo);
    expect(undo).toHaveFocus();

    finishUndo();
    expect(await screen.findByText(text.restored(ADA.name))).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveFocus();
  });

  it('says so when undoing fails, and lets the owner try again', async () => {
    restoreMock.mockRejectedValue(new DataUnavailableError('person.mark_relevant'));
    const { user } = renderNotice();
    await user.click(screen.getByRole('button', { name: text.undoLabel(ADA.name) }));

    expect(await screen.findByRole('alert')).toHaveTextContent(text.undoFailed(ADA.name));
    expect(screen.getByRole('button', { name: text.undoLabel(ADA.name) })).toBeEnabled();
  });

  it('gives the keyboard to the message when undoing fails, and brings it on screen', async () => {
    restoreMock.mockRejectedValue(new DataUnavailableError('person.mark_relevant'));
    const { container, user } = renderNotice();
    await user.click(screen.getByRole('button', { name: text.undoLabel(ADA.name) }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveFocus();
    expect(scrollIntoViewCalls(alert)).toHaveLength(1);
    await expectNoAxeViolations(container);
  });

  it('says so again when another try fails too', async () => {
    restoreMock.mockRejectedValue(new DataUnavailableError('person.mark_relevant'));
    const { user } = renderNotice();
    const undo = screen.getByRole('button', { name: text.undoLabel(ADA.name) });
    await user.click(undo);
    await screen.findByRole('alert');

    await user.click(undo);

    expect(restoreMock).toHaveBeenCalledTimes(2);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveFocus();
    });
    expect(scrollIntoViewCalls(screen.getByRole('alert'))).toHaveLength(1);
  });
});
