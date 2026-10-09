/**
 * The brand mark as the app icon draws it: three round strokes (two threads
 * curving into one line) placed on a 64-unit rounded square, with the exact
 * numbers of the owner's `threadline-icon.svg`. The Logo component draws the
 * same three paths in their own 264×160 box.
 */
import { type Point, polylineDistance } from './png.ts';

/** How the icon maps the mark's own coordinates into its 64-unit square. */
const SCALE = 0.1704;
const OFFSET: Point = [11.6 - 159 * SCALE, 20.6 - 214 * SCALE];
/** Straight pieces a curve is cut into; 32 keeps the error far below a pixel at 512px. */
const CURVE_STEPS = 32;

export const MARK = {
  box: 64,
  cornerRadius: 14,
  strokeWidth: 24 * SCALE,
} as const;

/** The two threads: a straight start, then a cubic curve into the line. */
const THREAD_LINE_START: Point = [159, 281];
const THREAD_LINE_END: Point = [397, 281];
const THREADS: readonly { start: Point; curve: readonly [Point, Point, Point, Point] }[] = [
  { start: [159, 214], curve: [[182, 214], [222, 214], [228, 281], [268, 281]] },
  { start: [159, 348], curve: [[182, 348], [222, 348], [228, 281], [268, 281]] },
];

/** A point of the mark's own coordinates placed in the icon's box. */
function placed([x, y]: Point): Point {
  return [x * SCALE + OFFSET[0], y * SCALE + OFFSET[1]];
}

/** The cubic Bézier p0–p3 flattened into `CURVE_STEPS` straight pieces. */
function flattenCubic([p0, p1, p2, p3]: readonly [Point, Point, Point, Point]): Point[] {
  return Array.from({ length: CURVE_STEPS + 1 }, (_, step) => {
    const t = step / CURVE_STEPS;
    const u = 1 - t;
    const weights = [u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3];
    const at = (axis: 0 | 1) =>
      weights[0]! * p0[axis] + weights[1]! * p1[axis] + weights[2]! * p2[axis] + weights[3]! * p3[axis];
    return [at(0), at(1)];
  });
}

/** The mark's three strokes as polylines in the icon's box. */
const STROKES: readonly (readonly Point[])[] = [
  ...THREADS.map(({ start, curve }) => [start, ...flattenCubic(curve)].map(placed)),
  [THREAD_LINE_START, THREAD_LINE_END].map(placed),
];

/** Signed distance, in box units, from a point in the icon's box to the mark's round-capped strokes. */
export function markDistance(point: Point): number {
  const nearest = Math.min(...STROKES.map((stroke) => polylineDistance(point, stroke)));
  return nearest - MARK.strokeWidth / 2;
}
