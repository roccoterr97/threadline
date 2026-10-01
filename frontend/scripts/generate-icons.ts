/**
 * Draws Threadline's home-screen icons as PNG files in `public/icons/`.
 *
 * The mark is the one the Logo component draws — a tick on a rounded square —
 * and its colours are read from the design tokens, so the icons follow the
 * tokens rather than keeping their own copy. It needs nothing beyond Node
 * itself: each pixel's coverage comes from its distance to the shapes, and the
 * PNG is written with Node's built-in zlib.
 *
 * Run with `npm run icons` after changing the mark or the accent colour, and
 * commit the files it writes.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { crc32, deflateSync } from 'node:zlib';

const FRONTEND_ROOT = new URL('../', import.meta.url);
const TOKENS_FILE = new URL('src/theme/tokens.css', FRONTEND_ROOT);
const ICONS_DIR = new URL('public/icons/', FRONTEND_ROOT);

/** The Logo component's drawing, in its own 32-unit box. */
const MARK = {
  box: 32,
  cornerRadius: 8,
  tick: [
    [9, 16.5],
    [13.5, 21],
    [23, 11.5],
  ],
  strokeWidth: 3,
} as const;

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

type Rgb = readonly [number, number, number];
type Point = readonly [number, number];

const HEX_COLOUR = /^#([0-9a-f]{6})$/i;
const CHANNEL_MAX = 255;
const BYTES_PER_PIXEL = 4;
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const PNG_BIT_DEPTH = 8;
const PNG_COLOUR_TYPE_RGBA = 6;
const PNG_FILTER_NONE = 0;

/** Reads a light-theme token (its first definition in tokens.css) as RGB. */
function readToken(css: string, name: string): Rgb {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`, 'i').exec(css);
  const hex = HEX_COLOUR.exec(match?.[1] ?? '')?.[1];
  if (!hex) throw new Error(`Token --${name} is missing or not a #rrggbb colour`);
  const value = Number.parseInt(hex, 16);
  return [(value >> 16) & CHANNEL_MAX, (value >> 8) & CHANNEL_MAX, value & CHANNEL_MAX];
}

/** Signed distance from a point to a rounded square centred in the box. */
function roundedSquareDistance([x, y]: Point, half: number, radius: number): number {
  const qx = Math.abs(x) - (half - radius);
  const qy = Math.abs(y) - (half - radius);
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
  return outside + Math.min(Math.max(qx, qy), 0) - radius;
}

/** Distance from a point to the segment a–b. */
function segmentDistance([px, py]: Point, [ax, ay]: Point, [bx, by]: Point): number {
  const dx = bx - ax;
  const dy = by - ay;
  const t = Math.min(Math.max(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0), 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** Signed distance to the tick's round-capped stroke. */
function tickDistance(point: Point): number {
  const [first, middle, last] = MARK.tick;
  const nearest = Math.min(segmentDistance(point, first, middle), segmentDistance(point, middle, last));
  return nearest - MARK.strokeWidth / 2;
}

/** How much of a one-pixel-wide sample a shape covers, from its signed distance in pixels. */
function coverage(distancePx: number): number {
  return Math.min(Math.max(0.5 - distancePx, 0), 1);
}

/** One pixel's colour and opacity, sampled at its centre. */
function shadePixel(point: Point, spec: IconSpec, colours: { accent: Rgb; tick: Rgb }): number[] {
  const pxPerUnit = spec.size / MARK.box;
  const half = MARK.box / 2;
  const centred: Point = [point[0] - half, point[1] - half];
  const background =
    spec.shape === 'full' ? 1 : coverage(roundedSquareDistance(centred, half, MARK.cornerRadius) * pxPerUnit);
  const tick = coverage(tickDistance(point) * pxPerUnit);
  const colour = colours.accent.map((channel, index) =>
    Math.round(channel + ((colours.tick[index] ?? channel) - channel) * tick),
  );
  return [...colour, Math.round(background * CHANNEL_MAX)];
}

/** Draws one icon as raw PNG scanlines (a filter byte, then RGBA per pixel). */
function drawScanlines(spec: IconSpec, colours: { accent: Rgb; tick: Rgb }): Buffer {
  const rowBytes = 1 + spec.size * BYTES_PER_PIXEL;
  const raw = Buffer.alloc(rowBytes * spec.size);
  const unitsPerPx = MARK.box / spec.size;
  for (let row = 0; row < spec.size; row += 1) {
    raw[row * rowBytes] = PNG_FILTER_NONE;
    for (let column = 0; column < spec.size; column += 1) {
      const point: Point = [(column + 0.5) * unitsPerPx, (row + 0.5) * unitsPerPx];
      raw.set(shadePixel(point, spec, colours), row * rowBytes + 1 + column * BYTES_PER_PIXEL);
    }
  }
  return raw;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const typeAndData = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(typeAndData));
  return Buffer.concat([length, typeAndData, checksum]);
}

/** Wraps square RGBA scanlines in a PNG file. */
function encodePng(size: number, scanlines: Buffer): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.writeUInt8(PNG_BIT_DEPTH, 8);
  header.writeUInt8(PNG_COLOUR_TYPE_RGBA, 9);
  return Buffer.concat([
    PNG_SIGNATURE,
    pngChunk('IHDR', header),
    pngChunk('IDAT', deflateSync(scanlines)),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function main(): void {
  const css = readFileSync(TOKENS_FILE, 'utf8');
  const colours = { accent: readToken(css, 'tracker-accent'), tick: readToken(css, 'tracker-accent-fg') };
  mkdirSync(ICONS_DIR, { recursive: true });
  for (const spec of ICONS) {
    writeFileSync(new URL(spec.fileName, ICONS_DIR), encodePng(spec.size, drawScanlines(spec, colours)));
  }
}

main();
