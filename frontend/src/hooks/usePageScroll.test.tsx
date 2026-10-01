import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePageScroll } from './usePageScroll';

function Frame({ children }: { children: React.ReactNode }) {
  usePageScroll();
  const navigate = useNavigate();
  return (
    <>
      <Link to="/people/p-01">Open a person</Link>
      <Link to="/?type=startup">Filter the list</Link>
      <button
        type="button"
        onClick={() => {
          void navigate(-1);
        }}
      >
        Back
      </button>
      {children}
    </>
  );
}

function renderPages() {
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<Frame>List</Frame>} />
        <Route path="/people/:personId" element={<Frame>Person</Frame>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

/** Pretends the visitor scrolled the window to `top`. */
function scrollWindowTo(top: number) {
  act(() => {
    Object.defineProperty(window, 'scrollY', { value: top, configurable: true });
    fireEvent.scroll(window);
  });
}

const scrollTo = vi.fn();

beforeEach(() => {
  scrollTo.mockReset();
  vi.stubGlobal('scrollTo', scrollTo);
  Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
});

describe('usePageScroll', () => {
  it('starts a newly opened page at the top', async () => {
    const user = renderPages();
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));

    expect(await screen.findByText('Person')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
  });

  it('puts the list back where it was on going back', async () => {
    const user = renderPages();
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    scrollWindowTo(0);
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('leaves the scroll alone when only the filters change', async () => {
    const user = renderPages();
    scrollWindowTo(600);
    await user.click(screen.getByRole('link', { name: 'Filter the list' }));

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
