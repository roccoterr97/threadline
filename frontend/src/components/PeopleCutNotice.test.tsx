import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PEOPLE_MAX_ROWS } from '../constants/dashboard';
import * as copy from '../copy/en';
import { PeopleCutNotice } from './PeopleCutNotice';

describe('PeopleCutNotice', () => {
  it('says older people are left out when the list hit the cap', () => {
    render(<PeopleCutNotice shown={PEOPLE_MAX_ROWS} />);
    expect(screen.getByText(copy.states.peopleCut(PEOPLE_MAX_ROWS))).toBeInTheDocument();
  });

  it('stays silent for a list that was read in full', () => {
    const { container } = render(<PeopleCutNotice shown={PEOPLE_MAX_ROWS - 1} />);
    expect(container).toBeEmptyDOMElement();
  });
});
