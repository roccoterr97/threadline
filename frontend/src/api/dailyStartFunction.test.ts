// @vitest-environment node
/**
 * Tests for the on-time morning start: the scheduled path of the "refresh-now"
 * Edge Function (supabase/functions/refresh-now/daily.ts). Deno is not part of
 * this project's tool chain, so the function's pure module is tested here,
 * with the database and GitHub replaced by in-memory stand-ins.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  anyOnOwnerDate,
  buildRunsQuery,
  countsAsStarted,
  DAILY_START_KEY_HEADER,
  DailyStartCode,
  dueToday,
  handleDailyStart,
  keysMatch,
  minutesPastMidnight,
  ownerMoment,
  readWorkflowRuns,
  usableKey,
  type DailyStartPorts,
  type DayClaim,
  type OwnerSchedule,
} from '../../../supabase/functions/refresh-now/daily.ts';
import {
  RefreshCode,
  RefreshTarget,
  StoreError,
  type GitHubConfig,
} from '../../../supabase/functions/refresh-now/refresh.ts';

const KEY = 'a-shared-key-of-more-than-thirty-two-characters';
const GITHUB_TOKEN = 'github_pat_secret_value';
const GITHUB_CONFIG: GitHubConfig = {
  target: RefreshTarget.GitHub,
  token: GITHUB_TOKEN,
  repository: 'someone/threadline',
  ref: 'main',
};
const PARIS_AT_SEVEN: OwnerSchedule = { timeZone: 'Europe/Paris', runAt: '07:00:00' };

// Paris is two hours ahead of UTC in summer time.
const PARIS_06_45 = new Date('2026-10-06T04:45:00Z');
const PARIS_07_15 = new Date('2026-10-06T05:15:00Z');

interface WorldOptions {
  now?: Date;
  schedule?: OwnerSchedule | null;
  recordedRuns?: Date[];
  githubRuns?: unknown[];
}

/** The function's ports over an in-memory claims table, as the database keeps it. */
function world(overrides: Partial<DailyStartPorts> = {}, options: WorldOptions = {}) {
  const claims = new Map<string, DayClaim>();
  let issued = 0;
  const ports: DailyStartPorts = {
    config: GITHUB_CONFIG,
    configuredKey: KEY,
    now: () => options.now ?? PARIS_07_15,
    readSchedule: vi.fn(() =>
      Promise.resolve(options.schedule === undefined ? PARIS_AT_SEVEN : options.schedule),
    ),
    readDailyRuns: vi.fn(() => Promise.resolve(options.recordedRuns ?? [])),
    claimDay: vi.fn((ownerDate: string) => {
      if (claims.has(ownerDate)) return Promise.resolve(null);
      issued += 1;
      const claim = { id: `claim-${issued}` };
      claims.set(ownerDate, claim);
      return Promise.resolve(claim);
    }),
    releaseDay: vi.fn((claim: DayClaim) => {
      for (const [ownerDate, held] of claims) if (held.id === claim.id) claims.delete(ownerDate);
      return Promise.resolve();
    }),
    send: vi.fn(() => Promise.resolve(204)),
    fetchJson: vi.fn(() =>
      Promise.resolve({ status: 200, body: { workflow_runs: options.githubRuns ?? [] } }),
    ),
    log: vi.fn(),
    ...overrides,
  };
  return { ports, claims };
}

function call(key: string | null = KEY, method = 'POST'): Request {
  const headers: Record<string, string> = key === null ? {} : { [DAILY_START_KEY_HEADER]: key };
  return new Request('https://project.supabase.co/functions/v1/refresh-now/daily-start', {
    method,
    headers,
  });
}

async function answer(response: Response) {
  return { status: response.status, body: (await response.json()) as Record<string, unknown> };
}

function githubRun(createdAt: string, extra: Record<string, unknown> = {}) {
  return {
    display_title: 'Threadline daily run',
    created_at: createdAt,
    status: 'completed',
    conclusion: 'success',
    ...extra,
  };
}

describe('the shared key', () => {
  it('matches only the very same key', () => {
    expect(keysMatch(KEY, KEY)).toBe(true);
    expect(keysMatch(`${KEY.slice(0, -1)}X`, KEY)).toBe(false);
    expect(keysMatch(KEY.slice(0, -1), KEY)).toBe(false);
    expect(keysMatch(`${KEY}X`, KEY)).toBe(false);
    expect(keysMatch(null, KEY)).toBe(false);
    expect(keysMatch('', KEY)).toBe(false);
  });

  it('treats a missing or short configured key as no key', () => {
    expect(usableKey(undefined)).toBeNull();
    expect(usableKey('short')).toBeNull();
    expect(usableKey(`  ${KEY}  `)).toBe(KEY);
  });
});

describe("the owner's clock", () => {
  it('reads the date and time in the owner zone, not the server one', () => {
    const lateEvening = new Date('2026-10-05T22:30:00Z');

    expect(ownerMoment(lateEvening, 'Europe/Paris')).toEqual({ date: '2026-10-06', minutes: 30 });
    expect(ownerMoment(lateEvening, 'UTC')).toEqual({ date: '2026-10-05', minutes: 22 * 60 + 30 });
    expect(ownerMoment(lateEvening, 'America/New_York')).toEqual({
      date: '2026-10-05',
      minutes: 18 * 60 + 30,
    });
  });

  it('refuses a zone nobody knows instead of guessing', () => {
    expect(ownerMoment(PARIS_07_15, 'Mars/Olympus')).toBeNull();
    expect(dueToday({ timeZone: 'Mars/Olympus', runAt: '07:00:00' }, PARIS_07_15)).toEqual({
      due: false,
      code: DailyStartCode.NotSetUp,
    });
  });

  it('reads the daily time as Postgres writes it', () => {
    expect(minutesPastMidnight('07:00:00')).toBe(420);
    expect(minutesPastMidnight('07:05')).toBe(425);
    expect(minutesPastMidnight('23:59:59.5')).toBe(1439);
    expect(minutesPastMidnight('24:00:00')).toBeNull();
    expect(minutesPastMidnight('7 am')).toBeNull();
  });
});

describe('dueToday', () => {
  it('waits before the daily time and starts from it on', () => {
    expect(dueToday(PARIS_AT_SEVEN, PARIS_06_45)).toEqual({ due: false, code: DailyStartCode.TooEarly });
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-10-06T05:00:00Z'))).toEqual({
      due: true,
      ownerDate: '2026-10-06',
    });
    expect(dueToday(PARIS_AT_SEVEN, PARIS_07_15)).toEqual({ due: true, ownerDate: '2026-10-06' });
  });

  it('follows summer time: 07:00 in Paris is 05:00 UTC in summer and 06:00 in winter', () => {
    // Summer time starts on 29 March 2026.
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-03-28T05:10:00Z')).due).toBe(false);
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-03-28T06:10:00Z'))).toEqual({
      due: true,
      ownerDate: '2026-03-28',
    });
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-03-29T05:10:00Z'))).toEqual({
      due: true,
      ownerDate: '2026-03-29',
    });
    // It ends on 25 October 2026.
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-10-24T05:10:00Z')).due).toBe(true);
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-10-25T05:10:00Z')).due).toBe(false);
    expect(dueToday(PARIS_AT_SEVEN, new Date('2026-10-25T06:10:00Z')).due).toBe(true);
  });

  it("names the owner's date across midnight, where UTC still says yesterday", () => {
    const justAfterMidnight = { timeZone: 'Europe/Paris', runAt: '00:00:00' };

    expect(dueToday(justAfterMidnight, new Date('2026-10-05T22:30:00Z'))).toEqual({
      due: true,
      ownerDate: '2026-10-06',
    });
  });
});

describe('what counts as already run', () => {
  it("places each run on the owner's day", () => {
    const parisHalfPastMidnight = new Date('2026-10-05T22:30:00Z');
    const parisHalfPastEleven = new Date('2026-10-05T21:30:00Z');

    expect(anyOnOwnerDate([parisHalfPastMidnight], '2026-10-06', 'Europe/Paris')).toBe(true);
    expect(anyOnOwnerDate([parisHalfPastEleven], '2026-10-06', 'Europe/Paris')).toBe(false);
    expect(anyOnOwnerDate([parisHalfPastMidnight], '2026-10-06', 'UTC')).toBe(false);
  });

  it('counts a daily run that is waiting, going or went well, never one that failed', () => {
    const run = readWorkflowRuns({ workflow_runs: [githubRun('2026-10-06T05:00:00Z')] })?.[0];
    expect(run).toBeDefined();
    if (run === undefined) return;

    expect(countsAsStarted(run)).toBe(true);
    expect(countsAsStarted({ ...run, status: 'queued', conclusion: null })).toBe(true);
    expect(countsAsStarted({ ...run, conclusion: 'failure' })).toBe(false);
    expect(countsAsStarted({ ...run, conclusion: 'cancelled' })).toBe(false);
    expect(countsAsStarted({ ...run, title: 'Threadline refresh' })).toBe(false);
  });

  it("refuses an answer from GitHub that is not a list of runs", () => {
    expect(readWorkflowRuns(null)).toBeNull();
    expect(readWorkflowRuns({ workflow_runs: 'x' })).toBeNull();
    expect(readWorkflowRuns({ workflow_runs: [{ display_title: 1 }] })).toBeNull();
    expect(readWorkflowRuns({ workflow_runs: [githubRun('not a date')] })).toBeNull();
  });

  it("asks GitHub for the workflow's runs since a moment, with the token in the header only", () => {
    const request = buildRunsQuery(GITHUB_CONFIG, new Date('2026-10-05T04:15:00Z'));
    const url = new URL(request.url);

    expect(url.origin + url.pathname).toBe(
      'https://api.github.com/repos/someone/threadline/actions/workflows/threadline-run.yml/runs',
    );
    expect(url.searchParams.get('created')).toBe('>=2026-10-05T04:15:00.000Z');
    expect(url.searchParams.get('per_page')).toBe('100');
    expect(request.url).not.toContain(GITHUB_TOKEN);
    expect(request.init.headers.Authorization).toBe(`Bearer ${GITHUB_TOKEN}`);
  });
});

describe('handleDailyStart', () => {
  it('does nothing before the daily time', async () => {
    const { ports, claims } = world({}, { now: PARIS_06_45 });

    const { status, body } = await answer(await handleDailyStart(call(), ports));

    expect(status).toBe(200);
    expect(body.code).toBe(DailyStartCode.TooEarly);
    expect(ports.send).not.toHaveBeenCalled();
    expect(claims.size).toBe(0);
  });

  it('starts the daily run once the time has passed and nothing started yet', async () => {
    const { ports, claims } = world();

    const { status, body } = await answer(await handleDailyStart(call(), ports));

    expect(status).toBe(202);
    expect(body).toEqual({ code: DailyStartCode.Started, owner_date: '2026-10-06' });
    expect(ports.send).toHaveBeenCalledTimes(1);
    const [request] = vi.mocked(ports.send).mock.calls[0] ?? [];
    expect(request?.url).toBe(
      'https://api.github.com/repos/someone/threadline/actions/workflows/threadline-run.yml/dispatches',
    );
    expect(JSON.parse(request?.init.body ?? '{}')).toEqual({ ref: 'main', inputs: { mode: 'daily' } });
    expect([...claims.keys()]).toEqual(['2026-10-06']);
  });

  it('starts nothing more on a second call the same day', async () => {
    const { ports } = world();

    await handleDailyStart(call(), ports);
    const second = await answer(await handleDailyStart(call(), ports));

    expect(second.body.code).toBe(DailyStartCode.AlreadyStarted);
    expect(ports.send).toHaveBeenCalledTimes(1);
  });

  it('starts one run when two calls overlap', async () => {
    const { ports } = world();

    const answers = await Promise.all([
      handleDailyStart(call(), ports).then(answer),
      handleDailyStart(call(), ports).then(answer),
    ]);

    expect(answers.map(({ body }) => body.code).sort()).toEqual(
      [DailyStartCode.AlreadyStarted, DailyStartCode.Started].sort(),
    );
    expect(ports.send).toHaveBeenCalledTimes(1);
  });

  it('starts again the next day', async () => {
    const { ports } = world();

    await handleDailyStart(call(), ports);
    ports.now = () => new Date('2026-10-07T05:15:00Z');
    const next = await answer(await handleDailyStart(call(), ports));

    expect(next.body).toEqual({ code: DailyStartCode.Started, owner_date: '2026-10-07' });
    expect(ports.send).toHaveBeenCalledTimes(2);
  });

  it.each([
    [401, RefreshCode.RunnerAuthFailed],
    [404, RefreshCode.RunnerNotFound],
    [422, RefreshCode.RunnerRejected],
    [500, RefreshCode.RunnerUnavailable],
  ])('gives the day back when GitHub answers %i, so the next call tries again', async (status, runner) => {
    const send = vi.fn().mockResolvedValueOnce(status).mockResolvedValue(204);
    const { ports, claims } = world({ send });

    const failed = await answer(await handleDailyStart(call(), ports));

    expect(failed.status).toBe(502);
    expect(failed.body).toEqual({ code: DailyStartCode.RunnerFailed, owner_date: '2026-10-06', runner });
    expect(claims.size).toBe(0);

    const retried = await answer(await handleDailyStart(call(), ports));
    expect(retried.body.code).toBe(DailyStartCode.Started);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('gives the day back when GitHub cannot be reached, and logs no message text', async () => {
    const send = vi.fn(() => Promise.reject(new TypeError(`fetch failed for ${GITHUB_TOKEN}`)));
    const { ports, claims } = world({ send });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body.runner).toBe(RefreshCode.RunnerUnavailable);
    expect(claims.size).toBe(0);
    expect(JSON.stringify(vi.mocked(ports.log).mock.calls)).not.toContain(GITHUB_TOKEN);
  });

  it("still answers GitHub's refusal when the day cannot be given back", async () => {
    const { ports } = world({
      send: vi.fn(() => Promise.resolve(500)),
      releaseDay: vi.fn(() => Promise.reject(new StoreError(RefreshCode.DatabaseUnavailable))),
    });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body.code).toBe(DailyStartCode.RunnerFailed);
    expect(ports.log).toHaveBeenCalledWith('daily_start.release_failed', {
      code: RefreshCode.DatabaseUnavailable,
    });
  });

  it("treats a daily run already recorded on the owner's day as done", async () => {
    // 00:30 in Paris on the 6th, still the 5th in UTC.
    const { ports, claims } = world({}, { recordedRuns: [new Date('2026-10-05T22:30:00Z')] });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body).toEqual({ code: DailyStartCode.AlreadyRan, owner_date: '2026-10-06' });
    expect(ports.send).not.toHaveBeenCalled();
    expect(claims.size).toBe(0);
  });

  it("does not count yesterday's run, even when UTC says it was today", async () => {
    const lateRun = new Date('2026-10-06T00:30:00Z');
    const { ports } = world(
      {},
      { now: new Date('2026-10-06T22:15:00Z'), recordedRuns: [lateRun], schedule: { timeZone: 'America/New_York', runAt: '18:00:00' } },
    );

    const { body } = await answer(await handleDailyStart(call(), ports));

    // 00:30 UTC on the 6th is 20:30 on the 5th in New York.
    expect(body).toEqual({ code: DailyStartCode.Started, owner_date: '2026-10-06' });
  });

  it('keeps the day and starts nothing when GitHub already started it, by its schedule or by hand', async () => {
    const { ports, claims } = world({}, { githubRuns: [githubRun('2026-10-06T05:02:00Z', { status: 'in_progress', conclusion: null })] });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body.code).toBe(DailyStartCode.AlreadyRan);
    expect(ports.send).not.toHaveBeenCalled();
    expect(claims.size).toBe(1);
  });

  it("starts the run when GitHub's only daily run today failed", async () => {
    const { ports } = world({}, { githubRuns: [githubRun('2026-10-06T05:02:00Z', { conclusion: 'failure' })] });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body.code).toBe(DailyStartCode.Started);
  });

  it('gives the day back when GitHub cannot say what already ran', async () => {
    const { ports, claims } = world({ fetchJson: vi.fn(() => Promise.resolve({ status: 503, body: null })) });

    const { body } = await answer(await handleDailyStart(call(), ports));

    expect(body.runner).toBe(RefreshCode.RunnerUnavailable);
    expect(ports.send).not.toHaveBeenCalled();
    expect(claims.size).toBe(0);
  });

  it.each([
    ['a wrong key', `${KEY.slice(0, -1)}X`],
    ['a shorter key', KEY.slice(0, 10)],
    ['no key at all', null],
  ])('turns away %s with 401 before anything else', async (_label, key) => {
    const { ports } = world();

    const { status, body } = await answer(await handleDailyStart(call(key), ports));

    expect(status).toBe(401);
    expect(body.code).toBe(DailyStartCode.NotAuthorised);
    expect(ports.readSchedule).not.toHaveBeenCalled();
    expect(ports.send).not.toHaveBeenCalled();
  });

  it('says "not set up" when the function has no key of its own, whatever the caller sends', async () => {
    const { ports } = world({ configuredKey: 'short' });

    const { status, body } = await answer(await handleDailyStart(call(), ports));

    expect(status).toBe(503);
    expect(body.code).toBe(DailyStartCode.NotSetUp);
    expect(ports.send).not.toHaveBeenCalled();
  });

  it('does nothing for an owner who runs the Claude cloud routine', async () => {
    const { ports } = world({
      config: {
        target: RefreshTarget.ClaudeRoutine,
        token: 'sk-ant-oat01-x',
        fireUrl: 'https://api.anthropic.com/v1/claude_code/routines/trig_abc/fire',
      },
    });

    const { status, body } = await answer(await handleDailyStart(call(), ports));

    expect(status).toBe(200);
    expect(body.code).toBe(DailyStartCode.NotGitHub);
    expect(ports.readSchedule).not.toHaveBeenCalled();
    expect(ports.send).not.toHaveBeenCalled();
  });

  it('says "not set up" without runner settings or without the settings row', async () => {
    const noConfig = world({ config: null });
    const noRow = world({}, { schedule: null });

    expect((await answer(await handleDailyStart(call(), noConfig.ports))).body.code).toBe(
      DailyStartCode.NotSetUp,
    );
    expect((await answer(await handleDailyStart(call(), noRow.ports))).body.code).toBe(
      DailyStartCode.NotSetUp,
    );
  });

  it('explains a database failure without starting anything', async () => {
    const missing = world({ readSchedule: vi.fn(() => Promise.reject(new StoreError(RefreshCode.NotSetUp))) });
    const down = world({ claimDay: vi.fn(() => Promise.reject(new StoreError(RefreshCode.DatabaseUnavailable))) });

    const first = await answer(await handleDailyStart(call(), missing.ports));
    const second = await answer(await handleDailyStart(call(), down.ports));

    expect(first).toEqual({ status: 503, body: { code: DailyStartCode.NotSetUp } });
    expect(second).toEqual({ status: 503, body: { code: DailyStartCode.DatabaseUnavailable } });
    expect(missing.ports.send).not.toHaveBeenCalled();
    expect(down.ports.send).not.toHaveBeenCalled();
  });

  it('refuses anything but POST', async () => {
    const { ports } = world();

    const { status } = await answer(await handleDailyStart(call(KEY, 'GET'), ports));

    expect(status).toBe(405);
  });

  it('never logs the key or the GitHub token', async () => {
    const { ports } = world({ send: vi.fn().mockResolvedValueOnce(401).mockResolvedValue(204) });

    await handleDailyStart(call(), ports);
    await handleDailyStart(call(), ports);

    const logged = JSON.stringify(vi.mocked(ports.log).mock.calls);
    expect(logged).toContain('daily_start.started');
    expect(logged).toContain('daily_start.runner_failed');
    expect(logged).not.toContain(KEY);
    expect(logged).not.toContain(GITHUB_TOKEN);
  });
});
