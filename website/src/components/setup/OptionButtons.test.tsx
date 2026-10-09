import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { OptionButtons } from './OptionButtons';

const OPTIONS = [
  { id: 'mac', label: 'Mac' },
  { id: 'windows', label: 'Windows', hint: 'Windows 10 or 11' },
];

describe('option buttons', () => {
  it('names each option by its words, not by its dot, and marks the chosen one', () => {
    render(<OptionButtons question="Which computer?" options={OPTIONS} value="mac" onChange={() => undefined} />);
    expect(screen.getByRole('radiogroup', { name: 'Which computer?' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Mac' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Windows Windows 10 or 11' })).toHaveAttribute('aria-checked', 'false');
  });

  it('reports the option pressed', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<OptionButtons question="Which computer?" options={OPTIONS} value={undefined} onChange={onChange} />);
    await user.click(screen.getByRole('radio', { name: /Windows/ }));
    expect(onChange).toHaveBeenCalledWith('windows');
  });
});
