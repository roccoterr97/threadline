// @vitest-environment node
/**
 * Tests for the "refresh-now" Edge Function's decisions
 * (supabase/functions/refresh-now/refresh.ts). Deno is not part of this
 * project's tool chain, so the function's pure module is tested here.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  buildDispatch,
  checkGuards,
  codeForDatabaseError,
  codeForRunnerStatus,
  corsHeaders,
  handleRefresh,
  OwnerCheck,
  readConfig,
  RefreshCode,
  RefreshTarget,
  REFRESH_COOLDOWN_MINUTES,
  StoreError,
  type Activity,
  type RefreshConfig,
  type RefreshPorts,
} from '../../../supabase/functions/refresh-now/refresh.ts';
import { REFRESH_SERVER_CODES } from '../domain/refresh';

const NOW = new Date('2026-09-29T10:00:00Z');
const DASHBOARD = 'https://threadline.example.test';
const GITHUB_TOKEN = 'github_pat_secret_value';
const ROUTINE_URL = 'https://api.anthropic.com/v1/claude_code/routines/trig_abc123/fire';

const GITHUB_CONFIG: RefreshConfig = {
  target: RefreshTarget.GitHub,
  token: GITHUB_TOKEN,
  repository: 'someone/threadline',
  ref: 'main',
};

function minutesAgo(minutes: number): Date {
  return new Date(NOW.getTime() - minutes * 60_000);
}

function settings(values: Record<string, string>) {
  return (name: string) => values[name];
}

const QUIET: Activity = { runningSince: null, lastRequestAt: null };
const CLAIM = { id: 'request-1' };

function ports(overrides: Partial<RefreshPorts> = {}): RefreshPorts {
  return {
    config: GITHUB_CONFIG,
    dashboardOrigin: DASHBOARD,
    now: () => NOW,
    checkOwner: vi.fn(() => Promise.resolve(OwnerCheck.Owner)),
    readActivity: vi.fn(() => Promise.resolve(QUIET)),
    claimRequest: vi.fn(() => Promise.resolve(CLAIM)),
    releaseRequest: vi.fn(() => Promise.resolve()),
    send: vi.fn(() => Promise.resolve(204)),
    log: vi.fn(),
    ...overrides,
  };
}

function post(headers: Record<string, string> = {}, method = 'POST'): Request {
  return new Request('https://project.supabase.co/functions/v1/refresh-now', {
    method,
    headers: { Origin: DASHBOARD, Authorization: 'Bearer user-jwt', ...headers },
  });
}

async function answer(response: Response) {
  return { status: response.status, body: (await response.json()) as Record<string, unknown> };
}

describe('readConfig', () => {
  it('defaults to GitHub on the main branch', () => {
    const config = readConfig(
      settings({ GITHUB_TOKEN_REFRESH: GITHUB_TOKEN, GITHUB_REPOSITORY: 'someone/threadline' }),
    );
    expect(config).toEqual(GITHUB_CONFIG);
  });

  it('reads the Claude routine settings', () => {
    const config = readConfig(
      settings({ REFRESH_TARGET: 'claude_routine', ROUTINE_FIRE_URL: ROUTINE_URL, ROUTINE_TOKEN: 't' }),
    );
    expect(config).toEqual({ target: RefreshTarget.ClaudeRoutine, token: 't', fireUrl: ROUTINE_URL });
  });

  it.each([
    ['a missing token', { GITHUB_REPOSITORY: 'someone/threadline' }],
    ['a repository that is not owner/name', { GITHUB_TOKEN_REFRESH: 't', GITHUB_REPOSITORY: 'x/../y/z' }],
    ['an unknown target', { REFRESH_TARGET: 'mac', GITHUB_TOKEN_REFRESH: 't' }],
    [
      'a fire address on another host',
      { REFRESH_TARGET: 'claude_routine', ROUTINE_FIRE_URL: 'https://evil.test/fire', ROUTINE_TOKEN: 't' },
    ],
  ])('refuses %s', (_label, values) => {
    expect(readConfig(settings(values))).toBeNull();
  });
});

describe('corsHeaders', () => {
  it('allows the dashboard and local development only', () => {
    expect(corsHeaders(DASHBOARD, `${DASHBOARD}/`)['Access-Control-Allow-Origin']).toBe(DASHBOARD);
    expect(corsHeaders('http://localhost:5173', DASHBOARD)['Access-Control-Allow-Origin']).toBe(
      'http://localhost:5173',
    );
    expect(corsHeaders('https://evil.test', DASHBOARD)).toEqual({ Vary: 'Origin' });
    expect(corsHeaders('https://evil.test', undefined)).toEqual({ Vary: 'Origin' });
  });
});

describe('checkGuards', () => {
  it('lets a refresh start when nothing is going on', () => {
    expect(checkGuards(QUIET, NOW)).toEqual({ code: RefreshCode.Started });
  });

  it('refuses while a run started in the last half hour is still going', () => {
    const verdict = checkGuards({ runningSince: minutesAgo(5), lastRequestAt: null }, NOW);
    expect(verdict).toEqual({ code: RefreshCode.AlreadyRunning });
  });

  it('ignores a "running" run that must have died long ago', () => {
    const verdict = checkGuards({ runningSince: minutesAgo(45), lastRequestAt: null }, NOW);
    expect(verdict).toEqual({ code: RefreshCode.Started });
  });

  it('asks to wait out the cool-down, in whole seconds', () => {
    const verdict = checkGuards({ runningSince: null, lastRequestAt: minutesAgo(4) }, NOW);
    expect(verdict).toEqual({
      code: RefreshCode.TooSoon,
      retryAfterSeconds: (REFRESH_COOLDOWN_MINUTES - 4) * 60,
    });
  });

  it('allows the next refresh once the cool-down is over', () => {
    const verdict = checkGuards(
      { runningSince: null, lastRequestAt: minutesAgo(REFRESH_COOLDOWN_MINUTES) },
      NOW,
    );
    expect(verdict).toEqual({ code: RefreshCode.Started });
  });
});

describe('buildDispatch', () => {
  it('starts the agreed workflow in refresh mode', () => {
    const request = buildDispatch(GITHUB_CONFIG);
    expect(request.url).toBe(
      'https://api.github.com/repos/someone/threadline/actions/workflows/threadline-run.yml/dispatches',
    );
    expect(request.init.headers.Authorization).toBe(`Bearer ${GITHUB_TOKEN}`);
    expect(JSON.parse(request.init.body)).toEqual({ ref: 'main', inputs: { mode: 'refresh' } });
  });

  it('fires the routine with the version header and the refresh text', () => {
    const request = buildDispatch({
      target: RefreshTarget.ClaudeRoutine,
      token: 'oat',
      fireUrl: ROUTINE_URL,
    });
    expect(request.url).toBe(ROUTINE_URL);
    expect(request.init.headers['anthropic-version']).toBe('2023-06-01');
    expect(JSON.parse(request.init.body)).toEqual({ text: 'mode: refresh' });
  });
});

describe('status mapping', () => {
  it.each([
    [204, null],
    [200, null],
    [401, RefreshCode.RunnerAuthFailed],
    [403, RefreshCode.RunnerAuthFailed],
    [404, RefreshCode.RunnerNotFound],
    [422, RefreshCode.RunnerRejected],
    [400, RefreshCode.RunnerRejected],
    [429, RefreshCode.RunnerRateLimited],
    [500, RefreshCode.RunnerUnavailable],
  ])('runner status %i → %s', (status, code) => {
    expect(codeForRunnerStatus(status)).toBe(code);
  });

  it('explains a missing table as "not set up" and an expired sign-in as such', () => {
    expect(codeForDatabaseError('PGRST205')).toBe(RefreshCode.NotSetUp);
    expect(codeForDatabaseError('PGRST301')).toBe(RefreshCode.NotSignedIn);
    expect(codeForDatabaseError('08006')).toBe(RefreshCode.DatabaseUnavailable);
    expect(codeForDatabaseError(undefined)).toBe(RefreshCode.DatabaseUnavailable);
  });
});

describe('handleRefresh', () => {
  it('starts a run, records it and says when', async () => {
    const deps = ports();
    const { status, body } = await answer(await handleRefresh(post(), deps));
    expect(status).toBe(202);
    expect(body).toEqual({ code: 'started', target: 'github', requested_at: NOW.toISOString() });
    expect(deps.claimRequest).toHaveBeenCalledWith(RefreshTarget.GitHub);
    expect(deps.releaseRequest).not.toHaveBeenCalled();
  });

  it('answers the browser pre-flight for the dashboard', async () => {
    const response = await handleRefresh(post({}, 'OPTIONS'), ports());
    expect(response.status).toBe(204);
    expect(response.headers.get('Access-Control-Allow-Origin')).toBe(DASHBOARD);
  });

  it('refuses another site', async () => {
    const deps = ports();
    const { status, body } = await answer(
      await handleRefresh(post({ Origin: 'https://evil.test' }), deps),
    );
    expect([status, body.code]).toEqual([403, 'origin_not_allowed']);
    expect(deps.checkOwner).not.toHaveBeenCalled();
  });

  it('refuses anything but POST', async () => {
    const { status } = await answer(await handleRefresh(post({}, 'GET'), ports()));
    expect(status).toBe(405);
  });

  it.each([
    [OwnerCheck.NotOwner, 403, 'not_owner'],
    [OwnerCheck.NotSignedIn, 401, 'not_signed_in'],
    [OwnerCheck.Unavailable, 503, 'database_unavailable'],
  ])('refuses a caller who is %s', async (check, status, code) => {
    const deps = ports({ checkOwner: () => Promise.resolve(check) });
    const result = await answer(await handleRefresh(post(), deps));
    expect([result.status, result.body.code]).toEqual([status, code]);
    expect(deps.send).not.toHaveBeenCalled();
  });

  it('refuses a request without a sign-in before asking the database', async () => {
    const request = new Request('https://project.supabase.co/functions/v1/refresh-now', {
      method: 'POST',
      headers: { Origin: DASHBOARD },
    });
    const deps = ports();
    const { status } = await answer(await handleRefresh(request, deps));
    expect(status).toBe(401);
    expect(deps.checkOwner).not.toHaveBeenCalled();
  });

  it('says "not set up" to the owner when the runner settings are missing', async () => {
    const { status, body } = await answer(await handleRefresh(post(), ports({ config: null })));
    expect([status, body.code]).toEqual([503, 'not_set_up']);
  });

  it('passes on the cool-down with a Retry-After header', async () => {
    const deps = ports({
      readActivity: () => Promise.resolve({ runningSince: null, lastRequestAt: minutesAgo(9) }),
    });
    const response = await handleRefresh(post(), deps);
    const { status, body } = await answer(response);
    expect([status, body.code, body.retry_after_seconds]).toEqual([429, 'too_soon', 60]);
    expect(response.headers.get('Retry-After')).toBe('60');
    expect(deps.send).not.toHaveBeenCalled();
  });

  it('explains a database failure without starting anything', async () => {
    const deps = ports({
      readActivity: () => Promise.reject(new StoreError(RefreshCode.NotSetUp)),
    });
    const { body } = await answer(await handleRefresh(post(), deps));
    expect(body.code).toBe('not_set_up');
    expect(deps.send).not.toHaveBeenCalled();
  });

  it('maps an expired runner token and never echoes the token', async () => {
    const deps = ports({ send: () => Promise.resolve(401) });
    const response = await handleRefresh(post(), deps);
    const text = await response.text();
    expect(response.status).toBe(502);
    expect(JSON.parse(text)).toEqual({ code: 'runner_auth_failed', target: 'github' });
    expect(text).not.toContain(GITHUB_TOKEN);
    expect(JSON.stringify(vi.mocked(deps.log).mock.calls)).not.toContain(GITHUB_TOKEN);
    expect(deps.releaseRequest).toHaveBeenCalledWith(CLAIM);
  });

  it('treats an unreachable runner as unavailable and logs no message text', async () => {
    const deps = ports({ send: () => Promise.reject(new TypeError(`fetch ${GITHUB_TOKEN}`)) });
    const { body } = await answer(await handleRefresh(post(), deps));
    expect(body.code).toBe('runner_unavailable');
    expect(JSON.stringify(vi.mocked(deps.log).mock.calls)).not.toContain(GITHUB_TOKEN);
  });

  it('tells a press that lost the race to wait, without starting a second run', async () => {
    const deps = ports({ claimRequest: () => Promise.resolve(null) });
    const response = await handleRefresh(post(), deps);
    const { status, body } = await answer(response);
    expect([status, body.code, body.retry_after_seconds]).toEqual([
      429,
      'too_soon',
      REFRESH_COOLDOWN_MINUTES * 60,
    ]);
    expect(deps.send).not.toHaveBeenCalled();
  });

  it('starts nothing when the cool-down cannot be claimed', async () => {
    const deps = ports({
      claimRequest: () => Promise.reject(new StoreError(RefreshCode.DatabaseUnavailable)),
    });
    const { status, body } = await answer(await handleRefresh(post(), deps));
    expect([status, body.code]).toEqual([503, 'database_unavailable']);
    expect(deps.send).not.toHaveBeenCalled();
  });

  it('still answers the runner refusal when the claim cannot be given back', async () => {
    const deps = ports({
      send: () => Promise.resolve(500),
      releaseRequest: () => Promise.reject(new StoreError(RefreshCode.DatabaseUnavailable)),
    });
    const { status, body } = await answer(await handleRefresh(post(), deps));
    expect([status, body.code]).toEqual([502, 'runner_unavailable']);
  });
});

describe('contract with the dashboard', () => {
  it('the dashboard knows every code the function can answer', () => {
    expect([...REFRESH_SERVER_CODES].sort()).toEqual(Object.values(RefreshCode).sort());
  });
});
