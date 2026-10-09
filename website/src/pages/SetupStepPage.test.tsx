import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearProgress, readProgress, setPlatform } from '../setup/progress';
import { FIXTURE_GUIDE } from '../test/__fixtures__/guide';
import { SetupStepPage } from './SetupStepPage';

vi.mock('../setup/guide', async () => {
  const { FIXTURE_GUIDE, FIXTURE_CLAUDE_WAY } = await import('../test/__fixtures__/guide');
  return { SETUP_GUIDE: FIXTURE_GUIDE, CLAUDE_WAY: FIXTURE_CLAUDE_WAY };
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/setup/step/:stepId" element={<SetupStepPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  clearProgress();
  setPlatform('mac');
});

describe('one step', () => {
  it('shows the step, its place on the thread and the words and line for this computer only', () => {
    renderAt('/setup/step/open-terminal');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Open a terminal');
    expect(
      screen.getByText((_, element) => element?.tagName === 'P' && element.textContent === 'Step 2 of 4 · Install'),
    ).toBeInTheDocument();
    expect(screen.getByText('Press ⌘ + Space.')).toBeInTheDocument();
    expect(screen.queryByText('Open the Start menu.')).not.toBeInTheDocument();
    expect(screen.getByText('open -a Terminal')).toBeInTheDocument();
    expect(screen.queryByText('start powershell')).not.toBeInTheDocument();
    expect(screen.getByText('Back')).toBeInTheDocument();
  });

  it('remembers the step as done when the reader goes on', async () => {
    const user = userEvent.setup();
    renderAt('/setup/step/open-terminal');
    await user.click(screen.getByRole('button', { name: 'Done, next' }));
    expect(readProgress().done).toEqual(['open-terminal']);
    const following = FIXTURE_GUIDE.core[1]?.steps[1]?.title ?? '';
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(following);
  });

  it('folds the reasons and the help away until asked', () => {
    renderAt('/setup/step/open-terminal');
    expect(screen.getByText('Why this step')).toBeInTheDocument();
    expect(screen.getByText('Did it not work?')).toBeInTheDocument();
    expect(FIXTURE_GUIDE.core[1]?.steps[0]?.intro.length).toBeGreaterThan(0);
  });

  it('says so for a step that does not exist', () => {
    renderAt('/setup/step/nope');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('There is no screen at this address');
  });
});
