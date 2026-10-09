import type { Platform } from '../lib/platform';
import type { SetupGuide, SetupPart, SetupStep } from './types';

/**
 * Questions the screens ask of the guide: which parts come in which order,
 * which steps a given computer sees, and how far along the reader is.
 */

/** The parts in reading order: the core ones, then the extras. */
export function orderedParts(guide: SetupGuide): readonly SetupPart[] {
  return [...guide.core, ...guide.extras];
}

/** The part at this address, or `null` when there is none. */
export function findPart(guide: SetupGuide, partId: string | undefined): SetupPart | null {
  if (partId === undefined) return null;
  return orderedParts(guide).find((part) => part.id === partId) ?? null;
}

/** What narrows the guide down to one reader: their computer and their answers. */
export interface Reader {
  platform: Platform;
  choices: Readonly<Record<string, string>>;
}

function forThisComputer(step: SetupStep, platform: Platform): boolean {
  return step.platforms === undefined || step.platforms.includes(platform);
}

/** A step limited to some answers shows for them, and for a reader who has not answered yet. */
function forThisAnswer(step: SetupStep, part: SetupPart, choices: Reader['choices']): boolean {
  if (step.onlyFor === undefined || part.choice === undefined) return true;
  const answer = choices[part.choice.id];
  return answer === undefined || step.onlyFor.includes(answer);
}

/** The steps of a part that apply to this reader. */
export function visibleSteps(part: SetupPart, reader: Reader): readonly SetupStep[] {
  return part.steps.filter(
    (step) => forThisComputer(step, reader.platform) && forThisAnswer(step, part, reader.choices),
  );
}

export interface PartProgress {
  done: number;
  total: number;
  complete: boolean;
}

/** How many of a part's steps for this reader are ticked. */
export function partProgress(part: SetupPart, done: readonly string[], reader: Reader): PartProgress {
  const steps = visibleSteps(part, reader);
  const ticked = steps.filter((step) => done.includes(step.id)).length;
  return { done: ticked, total: steps.length, complete: steps.length > 0 && ticked === steps.length };
}

/** How many of the core steps for this reader are ticked, across every core part. */
export function coreProgress(guide: SetupGuide, done: readonly string[], reader: Reader): PartProgress {
  const totals = guide.core.map((part) => partProgress(part, done, reader));
  const ticked = totals.reduce((sum, part) => sum + part.done, 0);
  const total = totals.reduce((sum, part) => sum + part.total, 0);
  return { done: ticked, total, complete: total > 0 && ticked === total };
}

/** The first core part with an unticked step, or `null` when every core step is done. */
export function firstUnfinishedPart(
  guide: SetupGuide,
  done: readonly string[],
  reader: Reader,
): SetupPart | null {
  return guide.core.find((part) => !partProgress(part, done, reader).complete) ?? null;
}

export interface PartNeighbours {
  previous: SetupPart | null;
  next: SetupPart | null;
}

/** The parts before and after this one in reading order. */
export function partNeighbours(guide: SetupGuide, partId: string): PartNeighbours {
  const parts = orderedParts(guide);
  const index = parts.findIndex((part) => part.id === partId);
  if (index === -1) return { previous: null, next: null };
  return { previous: parts[index - 1] ?? null, next: parts[index + 1] ?? null };
}

/** Where this part is: "Part 3 of 8" for a core part, or the extras. */
export function partPosition(guide: SetupGuide, part: SetupPart): { number: number; total: number } | null {
  const index = guide.core.findIndex((candidate) => candidate.id === part.id);
  if (index === -1) return null;
  return { number: index + 1, total: guide.core.length };
}
