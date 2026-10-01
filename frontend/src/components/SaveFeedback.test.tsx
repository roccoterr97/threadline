import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SaveFeedback } from './SaveFeedback';

const SAVED = 'Your correction was saved.';
const FAILED = 'We could not save your correction.';

describe('SaveFeedback', () => {
  it('reports a success politely, as a status', () => {
    render(<SaveFeedback outcome={{ tone: 'success', text: SAVED }} />);

    expect(screen.getByRole('status')).toHaveTextContent(SAVED);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('announces a failure at once, as an alert', () => {
    render(<SaveFeedback outcome={{ tone: 'error', text: FAILED }} />);

    expect(screen.getByRole('alert')).toHaveTextContent(FAILED);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('takes the focus and brings itself on screen when it appears', () => {
    render(<SaveFeedback outcome={{ tone: 'error', text: FAILED }} />);

    const banner = screen.getByRole('alert');
    expect(banner).toHaveFocus();
    expect(banner.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'nearest' });
  });

  it('leaves the keyboard alone when asked to, but still speaks', () => {
    render(<SaveFeedback outcome={{ tone: 'success', text: SAVED, keepFocus: true }} />);

    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent(SAVED);
    expect(banner).not.toHaveFocus();
    expect(banner.scrollIntoView).not.toHaveBeenCalled();
  });

  it('does not animate the scroll for someone who asked for less motion', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({ matches: true, media: query })),
    );

    render(<SaveFeedback outcome={{ tone: 'success', text: SAVED }} />);

    expect(screen.getByRole('status').scrollIntoView).toHaveBeenCalledWith({
      behavior: 'auto',
      block: 'nearest',
    });
  });

  it('comes back on screen when the outcome changes', () => {
    const { rerender } = render(<SaveFeedback outcome={{ tone: 'success', text: SAVED }} />);
    rerender(<SaveFeedback outcome={{ tone: 'error', text: FAILED }} />);

    expect(screen.getByRole('alert')).toHaveFocus();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(2);
  });
});
