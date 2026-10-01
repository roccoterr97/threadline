/** The Logo component's drawing, in its own 32-unit box: a tick on a rounded square. */
import { type Point, segmentDistance } from './png.ts';

export const MARK = {
  box: 32,
  cornerRadius: 8,
  tick: [
    [9, 16.5],
    [13.5, 21],
    [23, 11.5],
  ],
  strokeWidth: 3,
} as const;

/** Signed distance, in mark units, from a point in the mark's box to the tick's round-capped stroke. */
export function tickDistance(point: Point): number {
  const [first, middle, last] = MARK.tick;
  const nearest = Math.min(segmentDistance(point, first, middle), segmentDistance(point, middle, last));
  return nearest - MARK.strokeWidth / 2;
}
