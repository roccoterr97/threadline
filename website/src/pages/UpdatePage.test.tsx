import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { CHANGELOG_URL, INSTALL_LINE_MAC_LINUX, INSTALL_LINE_WINDOWS } from '../constants/links';
import { updatePage, updateSteps } from '../content/update';
import { UpdatePage } from './UpdatePage';

const keepWhitespace = (text: string) => text;

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/update']}>
      <UpdatePage />
    </MemoryRouter>,
  );
}

describe('UpdatePage', () => {
  it('shows the title, the change notes link and the three commands', () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: updatePage.title })).toBeInTheDocument();
    const changed = screen.getByRole('link', { name: updatePage.whatChanged });
    expect(changed).toHaveAttribute('href', CHANGELOG_URL);
    expect(changed).toHaveAttribute('target', '_blank');
    expect(screen.getByText(INSTALL_LINE_MAC_LINUX)).toBeInTheDocument();
    // The two lines stay two lines, so the newline must survive the match.
    expect(screen.getByText(updateSteps.publishCommand, { normalizer: keepWhitespace })).toBeInTheDocument();
    expect(screen.getByText(updateSteps.settingsCommand)).toBeInTheDocument();
  });

  it('switches the install line to the Windows one', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('radio', { name: 'Windows' }));
    expect(screen.getByText(INSTALL_LINE_WINDOWS)).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_LINE_MAC_LINUX)).not.toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Linux' }));
    expect(screen.getByText(INSTALL_LINE_MAC_LINUX)).toBeInTheDocument();
  });

  it('shows what to check and what to do if not', () => {
    renderPage();
    expect(screen.getByText('Check')).toBeInTheDocument();
    expect(screen.getByText('If not')).toBeInTheDocument();
  });
});
