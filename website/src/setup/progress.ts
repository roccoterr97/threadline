import { useSyncExternalStore } from 'react';
import { z } from 'zod';
import { SETUP_PROGRESS_KEY } from '../constants/site';
import { detectPlatform, isPlatform, type Platform } from '../lib/platform';
import { clearStored, readStored, writeStored } from '../lib/storage';

/**
 * The reader's place in the guided set-up, remembered in this browser only.
 *
 * It holds which computer they chose, which way in they chose, their answers
 * to the parts' questions (which mailbox…) and the ids of the steps they ticked. Ids the guide no longer knows are kept as they
 * are: an older browser must never lose a reader's ticks.
 */

export const SETUP_WAYS = ['claude', 'by-hand'] as const;
export type SetupWay = (typeof SETUP_WAYS)[number];

const progressSchema = z.object({
  platform: z.custom<Platform>(isPlatform),
  way: z.enum(SETUP_WAYS),
  done: z.array(z.string()),
  choices: z.record(z.string(), z.string()).default({}),
});

export type SetupProgress = z.infer<typeof progressSchema>;

const listeners = new Set<() => void>();
let cached: SetupProgress | null = null;
/** False once the browser refused a write: the progress then lives in memory for this visit. */
let storageWorks = true;

function defaultProgress(): SetupProgress {
  const userAgent = typeof navigator === 'undefined' ? '' : navigator.userAgent;
  return { platform: detectPlatform(userAgent), way: 'by-hand', done: [], choices: {} };
}

function sameChoices(a: Record<string, string>, b: Record<string, string>): boolean {
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((key) => a[key] === b[key]);
}

function sameProgress(a: SetupProgress, b: SetupProgress): boolean {
  return (
    a.platform === b.platform &&
    a.way === b.way &&
    a.done.length === b.done.length &&
    a.done.every((id, index) => id === b.done[index]) &&
    sameChoices(a.choices, b.choices)
  );
}

/**
 * What is remembered, or the defaults when nothing is. The same object comes
 * back while nothing has changed, so React can tell the two apart cheaply.
 */
export function readProgress(): SetupProgress {
  if (!storageWorks && cached !== null) return cached;
  const stored = readStored(SETUP_PROGRESS_KEY, progressSchema) ?? defaultProgress();
  if (cached !== null && sameProgress(cached, stored)) return cached;
  cached = stored;
  return cached;
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

function update(change: (current: SetupProgress) => SetupProgress): void {
  const next = change(readProgress());
  storageWorks = writeStored(SETUP_PROGRESS_KEY, next);
  cached = next;
  notify();
}

/** Ticks one step. Ticking it twice changes nothing. */
export function markDone(stepId: string): void {
  update((current) =>
    current.done.includes(stepId) ? current : { ...current, done: [...current.done, stepId] },
  );
}

/** Unticks one step. */
export function markNotDone(stepId: string): void {
  update((current) => ({ ...current, done: current.done.filter((id) => id !== stepId) }));
}

/** Remembers which computer the reader is setting up. */
export function setPlatform(platform: Platform): void {
  update((current) => ({ ...current, platform }));
}

/** Remembers which way in the reader chose. */
export function setWay(way: SetupWay): void {
  update((current) => ({ ...current, way }));
}

/** Remembers the answer to one part's question, such as which mailbox is read. */
export function setChoice(choiceId: string, optionId: string): void {
  update((current) => ({ ...current, choices: { ...current.choices, [choiceId]: optionId } }));
}

/** Forgets every tick and choice. */
export function clearProgress(): void {
  clearStored(SETUP_PROGRESS_KEY);
  cached = null;
  storageWorks = true;
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab of the same browser may tick a step too.
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

/** The remembered progress, kept in step with storage and with other tabs. */
export function useSetupProgress(): SetupProgress {
  return useSyncExternalStore(subscribe, readProgress, readProgress);
}
