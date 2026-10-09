import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DataUnavailableError } from '../lib/errors';
import { useReadQuery } from './useReadQuery';

function setup(queryFn: () => Promise<string>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useReadQuery({ queryKey: ['thing'], queryFn }), { wrapper });
  return { ...hook, queryClient };
}

describe('useReadQuery', () => {
  it('is pending until the first answer', () => {
    const { result } = setup(() => new Promise(() => undefined));
    expect(result.current).toMatchObject({ isPending: true, isError: false, isSuccess: false });
    expect(result.current.refreshFailed).toBe(false);
  });

  it('is ready with the data once it arrives', async () => {
    const { result } = setup(() => Promise.resolve('loaded'));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBe('loaded');
    expect(result.current.refreshFailed).toBe(false);
  });

  it('is an error when the first read fails, because there is nothing to show', async () => {
    const { result } = setup(() => Promise.reject(new DataUnavailableError('thing')));
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.data).toBeUndefined();
    expect(result.current.refreshFailed).toBe(false);
  });

  it('stays ready, with the old data, when a later update fails', async () => {
    const queryFn = vi.fn<() => Promise<string>>().mockResolvedValue('loaded');
    const { result, queryClient } = setup(queryFn);
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    queryFn.mockRejectedValue(new DataUnavailableError('thing'));
    await queryClient.refetchQueries({ queryKey: ['thing'] });

    await waitFor(() => {
      expect(result.current.refreshFailed).toBe(true);
    });
    expect(result.current).toMatchObject({ isSuccess: true, isError: false, data: 'loaded' });
  });

  it('clears the failure once a later update works', async () => {
    const queryFn = vi.fn<() => Promise<string>>().mockResolvedValue('first');
    const { result, queryClient } = setup(queryFn);
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    queryFn.mockRejectedValueOnce(new DataUnavailableError('thing'));
    await queryClient.refetchQueries({ queryKey: ['thing'] });
    await waitFor(() => {
      expect(result.current.refreshFailed).toBe(true);
    });

    queryFn.mockResolvedValue('second');
    await queryClient.refetchQueries({ queryKey: ['thing'] });

    await waitFor(() => {
      expect(result.current.refreshFailed).toBe(false);
    });
    expect(result.current.data).toBe('second');
  });
});
