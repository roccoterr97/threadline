import { FIXTURE_GUIDE } from '../test/__fixtures__/guide';
import {
  coreProgress,
  findPart,
  firstUnfinishedPart,
  orderedParts,
  partNeighbours,
  partPosition,
  partProgress,
  visibleSteps,
} from './guideNavigation';

const MAC = { platform: 'mac', choices: {} } as const;
const WINDOWS = { platform: 'windows', choices: {} } as const;

const INSTALL = FIXTURE_GUIDE.core[1];
const LINKEDIN = FIXTURE_GUIDE.extras[0];
if (INSTALL === undefined || LINKEDIN === undefined) throw new Error('fixture changed');

describe('finding parts', () => {
  it('lists the core parts first, then the extras', () => {
    expect(orderedParts(FIXTURE_GUIDE).map((part) => part.id)).toEqual([
      'before-you-start',
      'install',
      'final-check',
      'linkedin',
      'refresh-now',
    ]);
  });

  it('finds a part by its id, in the core or the extras, and nothing otherwise', () => {
    expect(findPart(FIXTURE_GUIDE, 'install')).toBe(INSTALL);
    expect(findPart(FIXTURE_GUIDE, 'linkedin')).toBe(LINKEDIN);
    expect(findPart(FIXTURE_GUIDE, 'nope')).toBeNull();
    expect(findPart(FIXTURE_GUIDE, undefined)).toBeNull();
  });

  it('gives a part its number among the core parts', () => {
    expect(partPosition(FIXTURE_GUIDE, INSTALL)).toEqual({ number: 2, total: 3 });
    expect(partPosition(FIXTURE_GUIDE, LINKEDIN)).toBeNull();
  });

  it('finds the neighbours, crossing from the core into the extras', () => {
    expect(partNeighbours(FIXTURE_GUIDE, 'before-you-start').previous).toBeNull();
    expect(partNeighbours(FIXTURE_GUIDE, 'final-check').next?.id).toBe('linkedin');
    expect(partNeighbours(FIXTURE_GUIDE, 'refresh-now').next).toBeNull();
    expect(partNeighbours(FIXTURE_GUIDE, 'nope')).toEqual({ previous: null, next: null });
  });
});

describe('progress through parts', () => {
  it('hides steps meant for another computer', () => {
    expect(visibleSteps(INSTALL, MAC).map((step) => step.id)).toEqual(['open-terminal', 'run-install']);
    expect(visibleSteps(INSTALL, WINDOWS)).toHaveLength(3);
  });

  it('counts only the steps this computer sees', () => {
    expect(partProgress(INSTALL, ['open-terminal', 'allow-windows'], MAC)).toEqual({
      done: 1,
      total: 2,
      complete: false,
    });
    expect(partProgress(INSTALL, ['open-terminal', 'run-install'], MAC).complete).toBe(true);
    expect(partProgress(INSTALL, ['open-terminal', 'run-install'], WINDOWS).complete).toBe(false);
  });

  it('adds up the core parts and ignores the extras', () => {
    expect(coreProgress(FIXTURE_GUIDE, ['linkedin-sign-in'], MAC)).toEqual({
      done: 0,
      total: 4,
      complete: false,
    });
    expect(
      coreProgress(FIXTURE_GUIDE, ['have-accounts', 'open-terminal', 'run-install', 'first-run'], MAC)
        .complete,
    ).toBe(true);
  });

  it('points at the first core part with something left to do', () => {
    expect(firstUnfinishedPart(FIXTURE_GUIDE, [], MAC)?.id).toBe('before-you-start');
    expect(firstUnfinishedPart(FIXTURE_GUIDE, ['have-accounts', 'open-terminal'], MAC)?.id).toBe(
      'install',
    );
    expect(
      firstUnfinishedPart(
        FIXTURE_GUIDE,
        ['have-accounts', 'open-terminal', 'run-install', 'first-run'], MAC,
      ),
    ).toBeNull();
  });
});

describe('steps limited to an answer', () => {
  const step = (id: string, onlyFor?: readonly string[]) => ({
    id,
    title: id,
    intro: [],
    youDo: [],
    check: [],
    ifNot: [],
    ...(onlyFor === undefined ? {} : { onlyFor }),
  });
  const MAILBOX = {
    id: 'mailbox',
    title: 'Mailbox',
    summary: '',
    choice: {
      id: 'mailbox',
      question: 'Which?',
      options: [
        { id: 'gmail', label: 'Gmail' },
        { id: 'other', label: 'Other' },
      ],
    },
    steps: [step('choose'), step('gmail', ['gmail']), step('other', ['other']), step('outlook')],
  };

  it('shows every step until the reader answers', () => {
    expect(visibleSteps(MAILBOX, MAC).map((s) => s.id)).toEqual(['choose', 'gmail', 'other', 'outlook']);
  });

  it('keeps only the steps for the answer given', () => {
    const reader = { platform: 'mac', choices: { mailbox: 'gmail' } } as const;
    expect(visibleSteps(MAILBOX, reader).map((s) => s.id)).toEqual(['choose', 'gmail', 'outlook']);
    expect(partProgress(MAILBOX, ['choose', 'gmail', 'outlook'], reader).complete).toBe(true);
  });

  it('ignores an answer to a question the part does not ask', () => {
    const reader = { platform: 'mac', choices: { computer: 'gmail' } } as const;
    expect(visibleSteps(MAILBOX, reader)).toHaveLength(4);
  });
});
