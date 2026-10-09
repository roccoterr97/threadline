import { SETUP_GUIDE } from './guide';
import { useSetupProgress, type SetupProgress } from './progress';
import { locateScreen, neighbours, screenPath, type ScreenPlace, type WizardScreen } from './wizard';

export interface WizardPlace {
  progress: SetupProgress;
  screen: WizardScreen;
  back: string | null;
  nextScreen: WizardScreen | null;
  next: string | null;
  position: { number: number; total: number } | null;
}

/** Where a screen sits for the current reader: its neighbours and its place on the thread. */
export function useWizard(kind: WizardScreen['kind'], id?: string): WizardPlace | null {
  const progress = useSetupProgress();
  const place: ScreenPlace | null = locateScreen(SETUP_GUIDE, progress, kind, id);
  if (place === null) return null;
  const screen = place.sequence[place.index];
  if (screen === undefined) return null;
  const around = neighbours(place);
  const lastStep = [...place.sequence].reverse().find((candidate) => candidate.kind === 'step');
  const total = lastStep?.kind === 'step' ? lastStep.total : 0;
  const position = screen.kind === 'step' ? { number: screen.number, total: screen.total } : positionBefore(place, total);
  return {
    progress,
    screen,
    back: around.back === null ? null : screenPath(around.back),
    nextScreen: around.next,
    next: around.next === null ? null : screenPath(around.next),
    position,
  };
}

/** A question screen sits on the thread where the next step would. */
function positionBefore(place: ScreenPlace, total: number): { number: number; total: number } | null {
  if (total === 0) return null;
  const nextStep = place.sequence.slice(place.index + 1).find((screen) => screen.kind === 'step');
  if (nextStep?.kind === 'step') return { number: nextStep.number - 1, total };
  return { number: total, total };
}
