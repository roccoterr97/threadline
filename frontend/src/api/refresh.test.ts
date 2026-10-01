import { FunctionsFetchError, FunctionsHttpError, FunctionsRelayError } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { refresh } from '../copy/en';
import { getSupabaseClient } from '../lib/supabaseClient';
import { REFRESH_FUNCTION_NAME, requestRefresh } from './refresh';

vi.mock('../lib/supabaseClient', () => ({ getSupabaseClient: vi.fn() }));

const invoke = vi.fn();

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  vi.mocked(getSupabaseClient).mockReturnValue({ functions: { invoke } } as unknown as ReturnType<
    typeof getSupabaseClient
  >);
});

describe('requestRefresh', () => {
  it('posts to the refresh function and reads when the run was asked for', async () => {
    invoke.mockResolvedValue({
      data: { code: 'started', target: 'github', requested_at: '2026-09-29T10:00:00.000Z' },
      error: null,
    });
    await expect(requestRefresh()).resolves.toEqual({
      kind: 'started',
      requestedAt: new Date('2026-09-29T10:00:00.000Z'),
      target: 'github',
    });
    expect(invoke).toHaveBeenCalledWith(REFRESH_FUNCTION_NAME, { method: 'POST' });
  });

  it('passes on a refusal with its wait', async () => {
    invoke.mockResolvedValue({
      data: null,
      error: new FunctionsHttpError(
        jsonResponse({ code: 'too_soon', target: 'github', retry_after_seconds: 90 }, 429),
      ),
    });
    await expect(requestRefresh()).resolves.toEqual({
      kind: 'refused',
      code: 'too_soon',
      target: 'github',
      retryAfterSeconds: 90,
    });
  });

  it('recognises a function that has not been deployed', async () => {
    invoke.mockResolvedValue({
      data: null,
      error: new FunctionsHttpError(jsonResponse({ message: 'Function not found' }, 404)),
    });
    await expect(requestRefresh()).resolves.toMatchObject({ kind: 'refused', code: 'not_deployed' });
  });

  it('takes an unanswered request while online as a function that is not switched on', async () => {
    invoke.mockResolvedValue({ data: null, error: new FunctionsFetchError(new TypeError('x')) });
    await expect(requestRefresh()).resolves.toMatchObject({ code: 'unanswered' });
  });

  it('tells the owner the one command that switches Refresh now on', () => {
    const command = "Run 'uv run tracker setup refresh'";
    expect(refresh.refusals.not_deployed()).toContain(command);
    expect(refresh.refusals.unanswered()).toContain(command);
    expect(refresh.refusals.unreachable()).toContain('offline');
  });

  it('says "unreachable" when the browser is offline', async () => {
    const onLine = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    invoke.mockResolvedValue({ data: null, error: new FunctionsFetchError(new TypeError('x')) });
    await expect(requestRefresh()).resolves.toMatchObject({ code: 'unreachable' });
    onLine.mockRestore();
  });

  it.each([
    ['an unknown code', { data: { code: 'launch_rockets' }, error: null }],
    ['"started" without a time', { data: { code: 'started' }, error: null }],
    ['a relay failure', { data: null, error: new FunctionsRelayError({}) }],
    [
      'a body that is not JSON',
      { data: null, error: new FunctionsHttpError(new Response('<html>', { status: 500 })) },
    ],
  ])('treats %s as unexpected', async (_label, answer) => {
    invoke.mockResolvedValue(answer);
    await expect(requestRefresh()).resolves.toMatchObject({ code: 'unexpected' });
  });
});
