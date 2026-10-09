import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { DEMO_URL } from '../constants/links';
import { HomePage } from './HomePage';

describe('the home page', () => {
  it('opens with the line, the demo first, then the set-up', () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Every conversation, one clear line.');
    const demo = screen.getAllByRole('link', { name: 'Try the demo' })[0];
    expect(demo).toHaveAttribute('href', DEMO_URL);
    expect(demo).toHaveAttribute('target', '_blank');
    expect(screen.getAllByRole('link', { name: 'Set it up' })[0]).toHaveAttribute('href', '/setup');
  });

  it('shows the dashboard with meaningful descriptions', () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    const pictures = screen.getAllByRole('img');
    expect(pictures.length).toBe(3);
    pictures.forEach((picture) => expect(picture.getAttribute('alt')).not.toBe(''));
  });
});
