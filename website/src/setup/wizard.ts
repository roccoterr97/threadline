import type { Reader } from './guideNavigation';
import { visibleSteps } from './guideNavigation';
import type { SetupProgress } from './progress';
import type { PartChoice, SetupGuide, SetupPart, SetupStep } from './types';

/**
 * The set-up as a sequence of screens, one thing per screen. The core
 * sequence runs from "which computer" to "done"; each extra is its own short
 * sequence that ends on the same "done" screen.
 */
export type WizardScreen =
  | { kind: 'computer' }
  | { kind: 'way' }
  | { kind: 'claude' }
  | { kind: 'choice'; part: SetupPart; choice: PartChoice }
  | { kind: 'step'; part: SetupPart; step: SetupStep; number: number; total: number }
  | { kind: 'done' };

/** The address of a screen. */
export function screenPath(screen: WizardScreen): string {
  switch (screen.kind) {
    case 'computer':
      return '/setup/computer';
    case 'way':
      return '/setup/way';
    case 'claude':
      return '/setup/claude';
    case 'choice':
      return `/setup/choose/${screen.choice.id}`;
    case 'step':
      return `/setup/step/${screen.step.id}`;
    case 'done':
      return '/setup/done';
  }
}

/** A part's screens: its question, if it asks one, then its steps for this reader. */
function partScreens(part: SetupPart, reader: Reader): WizardScreen[] {
  const screens: WizardScreen[] = [];
  if (part.choice !== undefined) screens.push({ kind: 'choice', part, choice: part.choice });
  for (const step of visibleSteps(part, reader)) {
    screens.push({ kind: 'step', part, step, number: 0, total: 0 });
  }
  return screens;
}

/** Numbers the step screens 1..n among themselves. */
function numbered(screens: WizardScreen[]): WizardScreen[] {
  const total = screens.filter((screen) => screen.kind === 'step').length;
  let number = 0;
  return screens.map((screen) => {
    if (screen.kind !== 'step') return screen;
    number += 1;
    return { ...screen, number, total };
  });
}

/** Every screen of the main set-up, in order. */
export function coreSequence(guide: SetupGuide, reader: Reader): readonly WizardScreen[] {
  return numbered([
    { kind: 'computer' },
    { kind: 'way' },
    ...guide.core.flatMap((part) => partScreens(part, reader)),
    { kind: 'done' },
  ]);
}

/** The screens of one extra, or `null` when there is no such extra. */
export function extraSequence(
  guide: SetupGuide,
  partId: string,
  reader: Reader,
): readonly WizardScreen[] | null {
  const part = guide.extras.find((candidate) => candidate.id === partId);
  if (part === undefined) return null;
  return numbered([...partScreens(part, reader), { kind: 'done' }]);
}

export interface ScreenPlace {
  sequence: readonly WizardScreen[];
  index: number;
}

function sameScreen(screen: WizardScreen, kind: WizardScreen['kind'], id: string | undefined): boolean {
  if (screen.kind !== kind) return false;
  if (screen.kind === 'choice') return screen.choice.id === id;
  if (screen.kind === 'step') return screen.step.id === id;
  return true;
}

/** Finds a screen in the main sequence first, then in each extra's. */
export function locateScreen(
  guide: SetupGuide,
  reader: Reader,
  kind: WizardScreen['kind'],
  id?: string,
): ScreenPlace | null {
  const candidates = [
    coreSequence(guide, reader),
    ...guide.extras.map((part) => extraSequence(guide, part.id, reader) ?? []),
  ];
  for (const sequence of candidates) {
    const index = sequence.findIndex((screen) => sameScreen(screen, kind, id));
    if (index !== -1) return { sequence, index };
  }
  return null;
}

/** The screens before and after a place in a sequence. */
export function neighbours(place: ScreenPlace): { back: WizardScreen | null; next: WizardScreen | null } {
  return {
    back: place.sequence[place.index - 1] ?? null,
    next: place.sequence[place.index + 1] ?? null,
  };
}

/**
 * Where to go from the start page: the first screen for a newcomer, the
 * first unfinished step for a returning reader, "done" when nothing is left.
 */
export function resumeScreen(guide: SetupGuide, progress: SetupProgress): WizardScreen {
  const sequence = coreSequence(guide, progress);
  const first = sequence[0];
  if (first === undefined) return { kind: 'done' };
  if (progress.done.length === 0) return first;
  const unfinished = sequence.find(
    (screen) => screen.kind === 'step' && !progress.done.includes(screen.step.id),
  );
  return unfinished ?? { kind: 'done' };
}
