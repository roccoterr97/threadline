/**
 * Draws Threadline's home-screen icons as PNG files in `public/icons/`.
 *
 * The mark is the one the Logo component draws — a tick on a rounded square —
 * and its colours are read from the design tokens, so the icons follow the
 * tokens rather than keeping their own copy. It needs nothing beyond Node
 * itself (see `png.ts`).
 *
 * Run with `npm run icons` after changing the mark or the accent colour, and
 * commit the files it writes.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { MARK, tickDistance } from './logoMark.ts';
import {
  blend,
  CHANNEL_MAX,
  coverage,
  drawScanlines,
  encodePng,
  type Point,
  readToken,
  readTokens,
  type Rgb,
  roundedRectDistance,
} from './png.ts';

const ICONS_DIR = new URL('../public/icons/', import.meta.url);

/**
 * How each file fills its square. "Rounded" keeps the mark's rounded corners
 * on a see-through background; "full" fills the whole square, because Android
 * (maskable) and iPhone cut their own shape out of it.
 */
type Shape = 'rounded' | 'full';

interface IconSpec {
  fileName: string;
  size: number;
  shape: Shape;
}

const ICONS: readonly IconSpec[] = [
  { fileName: 'icon-192.png', size: 192, shape: 'rounded' },
  { fileName: 'icon-512.png', size: 512, shape: 'rounded' },
  { fileName: 'icon-maskable-512.png', size: 512, shape: 'full' },
  { fileName: 'apple-touch-icon-180.png', size: 180, shape: 'full' },
];

/** One pixel's colour and opacity; `pixel` is in image pixels. */
function shadePixel(pixel: Point, spec: IconSpec, colours: { accent: Rgb; tick: Rgb }): number[] {
  const unitsPerPx = MARK.box / spec.size;
  const point: Point = [pixel[0] * unitsPerPx, pixel[1] * unitsPerPx];
  const half = MARK.box / 2;
  const centred: Point = [point[0] - half, point[1] - half];
  const background =
    spec.shape === 'full'
      ? 1
      : coverage(roundedRectDistance(centred, half, half, MARK.cornerRadius) / unitsPerPx);
  const tick = coverage(tickDistance(point) / unitsPerPx);
  return [...blend(colours.accent, colours.tick, tick), Math.round(background * CHANNEL_MAX)];
}

function main(): void {
  const css = readTokens();
  const colours = { accent: readToken(css, 'tracker-accent'), tick: readToken(css, 'tracker-accent-fg') };
  mkdirSync(ICONS_DIR, { recursive: true });
  for (const spec of ICONS) {
    const scanlines = drawScanlines(spec.size, spec.size, (pixel) => shadePixel(pixel, spec, colours));
    writeFileSync(new URL(spec.fileName, ICONS_DIR), encodePng(spec.size, spec.size, scanlines));
  }
}

main();
