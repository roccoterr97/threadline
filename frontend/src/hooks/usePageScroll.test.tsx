import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { lazy, StrictMode, Suspense } from 'react';
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

/** The list and a person page; `entries` and `index` set where the history starts. */
function renderPages(entries: string[] = ['/'], index = 0) {
  const result = render(
    <MemoryRouter initialEntries={entries} initialIndex={index}>
      <Routes>
        <Route path="/" element={<Frame>List</Frame>} />
        <Route path="/people/:personId" element={<Frame>Person</Frame>} />
      </Routes>
    </MemoryRouter>,
  );
  return { ...result, user: userEvent.setup() };
}

/** Moves the window to `top` and tells the page, as the browser does. */
function moveWindowTo(top: number) {
  Object.defineProperty(window, 'scrollY', { value: top, configurable: true });
  window.dispatchEvent(new Event('scroll'));
}

/** Pretends the visitor scrolled the window to `top`. */
function scrollWindowTo(top: number) {
  act(() => {
    Object.defineProperty(window, 'scrollY', { value: top, configurable: true });
    fireEvent.scroll(window);
  });
}

/** Tells the page it has grown, as the browser's ResizeObserver would. */
let pageGrew = () => undefined;

class GrowthWatch {
  constructor(callback: () => void) {
    pageGrew = () => {
      callback();
    };
  }
  observe = vi.fn();
  disconnect = vi.fn(() => {
    pageGrew = () => undefined;
  });
}

/** The page's full height, as the browser would report it once the list has loaded. */
function setPageHeight(height: number) {
  Object.defineProperty(document.documentElement, 'scrollHeight', {
    value: height,
    configurable: true,
  });
}

/** Opens a person from a list scrolled to 1800, then goes back while the list is still short. */
async function backToShortList() {
  const { user } = renderPages();
  setPageHeight(3000);
  scrollWindowTo(1800);
  await user.click(screen.getByRole('link', { name: 'Open a person' }));
  setPageHeight(0);
  await user.click(screen.getByRole('button', { name: 'Back' }));
  expect(await screen.findByText('List')).toBeInTheDocument();
  return user;
}

/** Says how the browser opened this document, as its navigation timing would. */
function openedBy(type: NavigationTimingType) {
  const entry = {
    name: '',
    entryType: 'navigation',
    startTime: 0,
    duration: 0,
    toJSON: () => ({}),
    type,
  };
  vi.spyOn(performance, 'getEntriesByType').mockReturnValue([entry]);
}

/** Scrolls the page at `route` to `top`, then leaves it as a reload or another address would. */
function visitAndLeave(route: string, top: number) {
  const { unmount } = renderPages([route]);
  scrollWindowTo(top);
  fireEvent(window, new Event('pagehide'));
  unmount();
  // A new document starts at the top, the browser's own restoring being off.
  Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
  scrollTo.mockClear();
}

const scrollTo = vi.fn();

beforeEach(() => {
  scrollTo.mockReset();
  vi.stubGlobal('scrollTo', scrollTo);
  vi.stubGlobal('ResizeObserver', GrowthWatch);
  Object.defineProperty(window, 'scrollY', { value: 0, configurable: true });
  setPageHeight(0);
  window.sessionStorage.clear();
});

describe('usePageScroll', () => {
  it('starts a newly opened page at the top', async () => {
    const { user } = renderPages();
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));

    expect(await screen.findByText('Person')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
  });

  it('puts the list back where it was on going back', async () => {
    const { user } = renderPages();
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    scrollWindowTo(0);
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('keeps the list\'s place when opening a page scrolls the window at once', async () => {
    // In a browser the scroll to the top can be reported before the page has
    // finished switching over; it belongs to the new page, not the list.
    scrollTo.mockImplementation((_left: number, top: number) => {
      moveWindowTo(top);
    });
    const { user } = renderPages();
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('finds the place again after a filter change that needed no scrolling', async () => {
    const { user } = renderPages();
    scrollWindowTo(600);
    await user.click(screen.getByRole('link', { name: 'Filter the list' }));
    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 600);
  });

  it('puts a list that is still loading back in place once it is long enough', async () => {
    await backToShortList();
    act(() => {
      setPageHeight(3000);
      pageGrew();
    });
    expect(scrollTo).toHaveBeenCalledTimes(3);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);

    act(() => {
      setPageHeight(3500);
      pageGrew();
    });
    expect(scrollTo).toHaveBeenCalledTimes(3);
  });

  it('gets as close as it can to a place the shorter list no longer reaches', async () => {
    // Someone was hidden meanwhile, so the list never grows tall enough again.
    await backToShortList();
    act(() => {
      setPageHeight(1500);
      pageGrew();
    });

    // The browser stops the scroll at the bottom of the page.
    expect(scrollTo).toHaveBeenCalledTimes(3);
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('keeps waiting when the page is set aside for a moment while code loads', async () => {
    // As in the app, everything sits inside one Suspense boundary. When part
    // of the page waits for its code, React swaps in the fallback, clears the
    // frame's effects, and runs them again once the code is there.
    let codeLoaded = () => undefined;
    const LateCode = lazy(
      () =>
        new Promise<{ default: () => null }>((resolve) => {
          codeLoaded = () => {
            resolve({ default: () => null });
          };
        }),
    );
    const app = (extra: React.ReactNode) => (
      <StrictMode>
        <MemoryRouter>
          <Suspense fallback="Loading">
            <Routes>
              <Route path="/" element={<Frame>List{extra}</Frame>} />
              <Route path="/people/:personId" element={<Frame>Person</Frame>} />
            </Routes>
          </Suspense>
        </MemoryRouter>
      </StrictMode>
    );
    const user = userEvent.setup();
    const { rerender } = render(app(null));
    setPageHeight(3000);
    scrollWindowTo(1800);
    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    setPageHeight(0);
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('List')).toBeInTheDocument();

    rerender(app(<LateCode />));
    expect(screen.getByText('Loading')).toBeInTheDocument();
    codeLoaded();
    await waitFor(() => {
      expect(screen.queryByText('Loading')).not.toBeInTheDocument();
    });

    act(() => {
      setPageHeight(3000);
      pageGrew();
    });
    expect(scrollTo.mock.calls.filter(([, top]) => top === 1800)).toHaveLength(2);
  });

  it('stops waiting for the list as soon as the owner scrolls', async () => {
    await backToShortList();
    fireEvent.wheel(window);
    act(() => {
      setPageHeight(3000);
      pageGrew();
    });

    expect(scrollTo).toHaveBeenCalledTimes(2);
  });

  it('leaves the scroll alone when only the filters change', async () => {
    const { user } = renderPages();
    scrollWindowTo(600);
    await user.click(screen.getByRole('link', { name: 'Filter the list' }));

    expect(scrollTo).not.toHaveBeenCalled();
  });

  it('keeps the places for the tab when the page is left, and finds them after a reload', async () => {
    const first = renderPages();
    scrollWindowTo(1800);
    await first.user.click(screen.getByRole('link', { name: 'Open a person' }));
    fireEvent(window, new Event('pagehide'));
    first.unmount();

    // The reloaded tab has the same history: the list, then the person.
    const { user } = renderPages(['/', '/people/p-01'], 1);
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('keeps the places for the tab once the page is out of sight', async () => {
    // A phone may throw a tab in the background away without saying goodbye.
    const first = renderPages();
    scrollWindowTo(1800);
    await first.user.click(screen.getByRole('link', { name: 'Open a person' }));
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    fireEvent(document, new Event('visibilitychange'));
    first.unmount();

    const { user } = renderPages(['/', '/people/p-01'], 1);
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('does not write the places down while the page is still in sight', () => {
    renderPages();
    scrollWindowTo(1800);
    fireEvent(document, new Event('visibilitychange'));

    expect(window.sessionStorage.length).toBe(0);
  });

  it('puts the page back where it was after a reload', () => {
    visitAndLeave('/', 1800);
    openedBy('reload');
    setPageHeight(3000);
    renderPages();

    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('forgets an earlier visit\'s place when the address is opened afresh', async () => {
    // A typed address or a bookmark: the browser gives such an entry no key of
    // the router's, so the place kept for an earlier visit must not come back.
    visitAndLeave('/', 1800);
    const { user } = renderPages();
    expect(scrollTo).not.toHaveBeenCalled();

    await user.click(screen.getByRole('link', { name: 'Open a person' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(await screen.findByText('List')).toBeInTheDocument();
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
  });

  it('keeps apart the places of two pages that were each opened by address', () => {
    visitAndLeave('/', 1800);
    visitAndLeave('/people/p-01', 500);
    openedBy('back_forward');
    setPageHeight(3000);
    renderPages();

    expect(scrollTo).toHaveBeenLastCalledWith(0, 1800);
  });

  it('turns off the browser\'s own restoring while it is in charge', () => {
    // jsdom has no scroll restoring of its own; a browser starts on "auto".
    window.history.scrollRestoration = 'auto';
    const { unmount } = renderPages();
    expect(window.history.scrollRestoration).toBe('manual');

    unmount();
    expect(window.history.scrollRestoration).toBe('auto');
  });
});
