import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { Platform } from '../../lib/platform';
import type { Block } from '../../setup/types';
import { BlockView } from './BlockView';

function renderBlock(block: Block, platform: Platform = 'mac') {
  return render(
    <MemoryRouter>
      <BlockView block={block} platform={platform} />
    </MemoryRouter>,
  );
}

describe('BlockView', () => {
  it('draws a paragraph with its markup', () => {
    renderBlock({ kind: 'paragraph', text: 'Hello **you**' });
    expect(screen.getByText('you').tagName).toBe('STRONG');
  });

  it('shows a command only for the computers it names', () => {
    const block: Block = {
      kind: 'command',
      command: 'irm install.ps1 | iex',
      platforms: ['windows'],
      what: 'the Windows line',
    };
    const { unmount } = renderBlock(block, 'mac');
    expect(screen.queryByText('irm install.ps1 | iex')).toBeNull();
    unmount();
    renderBlock(block, 'windows');
    expect(screen.getByText('irm install.ps1 | iex')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy the Windows line' })).toBeInTheDocument();
  });

  it('hides a paragraph and a list meant for other computers', () => {
    const paragraph: Block = { kind: 'paragraph', text: 'Press ⌘ + Space.', platforms: ['mac'] };
    const steps: Block = { kind: 'steps', items: ['Open the Start menu.'], platforms: ['windows'] };
    const { unmount } = renderBlock(paragraph, 'windows');
    expect(screen.queryByText('Press ⌘ + Space.')).toBeNull();
    unmount();
    renderBlock(steps, 'linux');
    expect(screen.queryByRole('list')).toBeNull();
    renderBlock(steps, 'windows');
    expect(screen.getByText('Open the Start menu.')).toBeInTheDocument();
  });

  it('shows a command for every computer when none is named', () => {
    renderBlock({ kind: 'command', command: 'tracker run', what: 'the run line' }, 'linux');
    expect(screen.getByText('tracker run')).toBeInTheDocument();
  });

  it('numbers steps and bullets bullets', () => {
    const { unmount } = renderBlock({ kind: 'steps', items: ['One', 'Two'] });
    expect(screen.getByRole('list').tagName).toBe('OL');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    unmount();
    renderBlock({ kind: 'bullets', items: ['A', 'B', 'C'] });
    expect(screen.getByRole('list').tagName).toBe('UL');
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });

  it('boxes a value with a copy button', () => {
    renderBlock({ kind: 'value', value: 'https://x.netlify.app', what: 'the dashboard address' });
    expect(screen.getByText('https://x.netlify.app')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy the dashboard address' })).toBeInTheDocument();
  });

  it('draws notes and warnings as callouts with their label', () => {
    const { unmount } = renderBlock({ kind: 'note', text: 'Handy.' });
    expect(screen.getByRole('complementary')).toHaveTextContent('Good to know');
    expect(screen.getByText('Handy.')).toBeInTheDocument();
    unmount();
    renderBlock({ kind: 'warning', text: 'Mind this.' });
    expect(screen.getByRole('complementary')).toHaveTextContent('Careful');
  });

  it('draws a table with the first row as the header', () => {
    renderBlock({
      kind: 'table',
      rows: [
        ['Setting', 'Value'],
        ['Time zone', '`Europe/London`'],
      ],
    });
    expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Setting',
      'Value',
    ]);
    expect(screen.getByText('Europe/London').tagName).toBe('CODE');
    expect(screen.getAllByRole('row')).toHaveLength(2);
  });
});
