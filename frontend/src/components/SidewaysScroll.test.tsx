import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SidewaysScroll } from './SidewaysScroll';

const HINT = 'Scroll sideways to see every column.';

/** Gives the frame a size, since jsdom lays nothing out. */
function sizeFrame(scrollWidth: number, clientWidth: number, scrollLeft = 0): HTMLElement {
  const frame = screen.getByText('wide content').parentElement!;
  Object.defineProperty(frame, 'scrollWidth', { value: scrollWidth, configurable: true });
  Object.defineProperty(frame, 'clientWidth', { value: clientWidth, configurable: true });
  Object.defineProperty(frame, 'scrollLeft', { value: scrollLeft, configurable: true, writable: true });
  return frame;
}

function renderFrame() {
  return render(
    <SidewaysScroll hint={HINT}>
      <p>wide content</p>
    </SidewaysScroll>,
  );
}

/** The fade drawn over the hidden end. */
function fades(): number {
  return document.querySelectorAll('[aria-hidden="true"]').length;
}

describe('SidewaysScroll', () => {
  it('draws nothing extra while the content fits', () => {
    renderFrame();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    expect(fades()).toBe(0);
  });

  it('says to scroll and fades the hidden edge once the content is wider', () => {
    renderFrame();
    const frame = sizeFrame(600, 300);
    act(() => {
      frame.dispatchEvent(new Event('scroll'));
    });
    expect(screen.getByText(HINT)).toBeInTheDocument();
    expect(fades()).toBe(1);
  });

  it('keeps the fade in the middle and drops it at the end, keeping the hint', () => {
    renderFrame();
    const frame = sizeFrame(600, 300, 150);
    act(() => {
      frame.dispatchEvent(new Event('scroll'));
    });
    expect(fades()).toBe(1);

    frame.scrollLeft = 300;
    act(() => {
      frame.dispatchEvent(new Event('scroll'));
    });
    expect(fades()).toBe(0);
    expect(screen.getByText(HINT)).toBeInTheDocument();
  });
});
