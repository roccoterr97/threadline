import { describe, expect, it } from 'vitest';
import { FIXTURE_GUIDE } from '../test/__fixtures__/guide';
import type { SetupProgress } from './progress';
import { coreSequence, extraSequence, locateScreen, neighbours, resumeScreen, screenPath } from './wizard';

const fresh: SetupProgress = { platform: 'mac', way: 'by-hand', done: [], choices: {} };

describe('the main sequence', () => {
  it('asks the two questions, then every step for this computer, then ends', () => {
    const paths = coreSequence(FIXTURE_GUIDE, fresh).map(screenPath);
    expect(paths).toEqual([
      '/setup/computer',
      '/setup/way',
      '/setup/step/have-accounts',
      '/setup/step/open-terminal',
      '/setup/step/run-install',
      '/setup/step/first-run',
      '/setup/done',
    ]);
  });

  it('numbers the steps among themselves', () => {
    const steps = coreSequence(FIXTURE_GUIDE, { ...fresh, platform: 'windows' }).filter(
      (screen) => screen.kind === 'step',
    );
    expect(steps.map((screen) => (screen.kind === 'step' ? screen.number : 0))).toEqual([1, 2, 3, 4, 5]);
    expect(steps.every((screen) => screen.kind === 'step' && screen.total === 5)).toBe(true);
  });
});

describe('extras', () => {
  it('runs one extra and ends on the same done screen', () => {
    expect(extraSequence(FIXTURE_GUIDE, 'linkedin', fresh)?.map(screenPath)).toEqual([
      '/setup/step/linkedin-sign-in',
      '/setup/done',
    ]);
    expect(extraSequence(FIXTURE_GUIDE, 'nope', fresh)).toBeNull();
  });
});

describe('finding a screen', () => {
  it('finds a step in the main sequence and its neighbours', () => {
    const place = locateScreen(FIXTURE_GUIDE, fresh, 'step', 'open-terminal');
    expect(place?.index).toBe(3);
    const around = neighbours(place!);
    expect(around.back === null ? null : screenPath(around.back)).toBe('/setup/step/have-accounts');
    expect(around.next === null ? null : screenPath(around.next)).toBe('/setup/step/run-install');
  });

  it("finds an extra's step in that extra's sequence", () => {
    const place = locateScreen(FIXTURE_GUIDE, fresh, 'step', 'linkedin-sign-in');
    expect(place?.index).toBe(0);
    expect(neighbours(place!).back).toBeNull();
  });

  it('knows nothing of a step that does not exist', () => {
    expect(locateScreen(FIXTURE_GUIDE, fresh, 'step', 'nope')).toBeNull();
  });
});

describe('where to resume', () => {
  it('starts a newcomer at the first question', () => {
    expect(screenPath(resumeScreen(FIXTURE_GUIDE, fresh))).toBe('/setup/computer');
  });

  it('takes a returning reader to the first unfinished step', () => {
    const progress = { ...fresh, done: ['have-accounts', 'open-terminal'] };
    expect(screenPath(resumeScreen(FIXTURE_GUIDE, progress))).toBe('/setup/step/run-install');
  });

  it('ends when every step is done', () => {
    const progress = { ...fresh, done: ['have-accounts', 'open-terminal', 'run-install', 'first-run'] };
    expect(screenPath(resumeScreen(FIXTURE_GUIDE, progress))).toBe('/setup/done');
  });
});
