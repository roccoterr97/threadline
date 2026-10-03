import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { peopleListAddress } from '../lib/peopleListAddress';
import { PersonLink } from './PersonLink';

/** Prints where the person page would send the owner back to. */
function PersonStub() {
  return <p>{`Back to ${peopleListAddress(useLocation().state)}`}</p>;
}

function renderFrom(address: string) {
  render(
    <MemoryRouter initialEntries={[address]}>
      <Routes>
        <Route path="/people/:personId" element={<PersonStub />} />
        <Route
          path="*"
          element={
            <PersonLink personId="p-01" className="">
              Open
            </PersonLink>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe('PersonLink', () => {
  it('opens the person and takes the People page\'s filters along', async () => {
    const user = renderFrom('/?type=startup&sort=name');
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/people/p-01');

    await user.click(screen.getByRole('link', { name: 'Open' }));
    expect(screen.getByText('Back to /?type=startup&sort=name')).toBeInTheDocument();
  });

  it('takes nothing along from another page', async () => {
    const user = renderFrom('/review?type=startup');
    await user.click(screen.getByRole('link', { name: 'Open' }));
    expect(screen.getByText('Back to /')).toBeInTheDocument();
  });
});
