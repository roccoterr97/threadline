import { createContext, useContext } from 'react';
import { systemClock, type Clock } from './clock';

/**
 * The clock every screen reads "now" from.
 *
 * Nothing calls `new Date()` in a component, so a test can freeze time by
 * wrapping the tree in this provider.
 */
export const ClockContext = createContext<Clock>(systemClock);

export function useClock(): Clock {
  return useContext(ClockContext);
}
