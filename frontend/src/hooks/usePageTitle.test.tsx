import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { usePageTitle } from './usePageTitle';

describe('usePageTitle', () => {
  it('names the tab after the page and the app', () => {
    const initialProps: { page: string | null } = { page: 'People' };
    const { rerender } = renderHook(
      ({ page }) => {
        usePageTitle(page);
      },
      { initialProps },
    );
    expect(document.title).toBe('People – Threadline');

    rerender({ page: null });
    expect(document.title).toBe(copy.app.name);
  });
});
