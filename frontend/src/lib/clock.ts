/**
 * An injectable clock. Nothing in the app reads `Date.now()` directly, so every
 * time-dependent rule can be tested with a fixed moment.
 */
export interface Clock {
  now(): Date;
}

export const systemClock: Clock = {
  now: () => new Date(),
};

/** A clock frozen at one moment — for tests and for previewing a rule. */
export function fixedClock(moment: Date): Clock {
  return { now: () => new Date(moment.getTime()) };
}
