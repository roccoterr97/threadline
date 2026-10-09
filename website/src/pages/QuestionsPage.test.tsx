import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { SUPPORT_EMAIL } from '../constants/links';
import { PrivacyPage } from './PrivacyPage';
import { QuestionsPage } from './QuestionsPage';

describe('questions and privacy', () => {
  it('answers how to remove Threadline and says where to write', () => {
    render(
      <MemoryRouter>
        <QuestionsPage />
      </MemoryRouter>,
    );
    // Once in the margin's list of questions, once above the answer.
    expect(screen.getAllByText('How do I pause it, or remove it completely?')).toHaveLength(2);
    expect(screen.getByText(/delete your threadline copy on GitHub/)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: SUPPORT_EMAIL })[0]).toHaveAttribute('href', `mailto:${SUPPORT_EMAIL}`);
  });

  it('states that the site does not track anyone', () => {
    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Privacy');
    expect(screen.getByText(/No cookies, no analytics/)).toBeInTheDocument();
  });
});
