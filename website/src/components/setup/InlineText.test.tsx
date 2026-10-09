import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { InlineText } from './InlineText';

function renderText(text: string) {
  return render(
    <MemoryRouter>
      <p data-testid="out">
        <InlineText text={text} />
      </p>
    </MemoryRouter>,
  );
}

describe('InlineText', () => {
  it('draws bold as strong and code as code', () => {
    renderText('Press **Enter**, then type `tracker setup`.');
    expect(screen.getByText('Enter').tagName).toBe('STRONG');
    expect(screen.getByText('tracker setup').tagName).toBe('CODE');
    expect(screen.getByTestId('out')).toHaveTextContent('Press Enter, then type tracker setup.');
  });

  it('opens an outside link in a new tab, safely', () => {
    renderText('See [the guide](https://example.com/guide) first.');
    const link = screen.getByRole('link', { name: 'the guide' });
    expect(link).toHaveAttribute('href', 'https://example.com/guide');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noreferrer');
  });

  it('keeps a link to this website inside the app', () => {
    renderText('Start with [before you start](/setup/before-you-start).');
    const link = screen.getByRole('link', { name: 'before you start' });
    expect(link).toHaveAttribute('href', '/setup/before-you-start');
    expect(link).not.toHaveAttribute('target');
  });

  it('never turns anything else into a link', () => {
    renderText('Not [this](javascript:alert(1)) and not [that](ftp://x).');
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByTestId('out')).toHaveTextContent(
      'Not [this](javascript:alert(1)) and not [that](ftp://x).',
    );
  });

  it('shows HTML as plain text', () => {
    renderText('Type <script>alert("x")</script> and **<b>bold</b>**');
    const out = screen.getByTestId('out');
    expect(out.querySelector('script')).toBeNull();
    expect(out.querySelector('b')).toBeNull();
    expect(out).toHaveTextContent('Type <script>alert("x")</script> and <b>bold</b>');
  });

  it('leaves unfinished markup as it is', () => {
    renderText('A lone ** star and a `tick');
    expect(screen.getByTestId('out')).toHaveTextContent('A lone ** star and a `tick');
  });
});
