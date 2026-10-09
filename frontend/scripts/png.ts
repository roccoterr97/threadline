/**
 * The small drawing kit the image scripts share: reading colours from the
 * design tokens, shapes as signed distances (so edges come out smooth), and
 * writing RGBA pixels as a PNG with nothing but Node's own zlib.
 */
import { readFileSync } from 'node:fs';
import { crc32, deflateSync } from 'node:zlib';

export type Rgb = readonly [number, number, number];
export type Point = readonly [number, number];

const HEX_COLOUR = /^#([0-9a-f]{6})$/i;
export const CHANNEL_MAX = 255;
const BYTES_PER_PIXEL = 4;
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const PNG_BIT_DEPTH = 8;
const PNG_COLOUR_TYPE_RGBA = 6;
const PNG_FILTER_NONE = 0;

/** The design tokens file, read once per script run. */
export function readTokens(): string {
  return readFileSync(new URL('../src/theme/tokens.css', import.meta.url), 'utf8');
}

/** A light-theme token (its first definition in tokens.css) as RGB. */
export function readToken(css: string, name: string): Rgb {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`, 'i').exec(css);
  const hex = HEX_COLOUR.exec(match?.[1] ?? '')?.[1];
  if (!hex) throw new Error(`Token --${name} is missing or not a #rrggbb colour`);
  const value = Number.parseInt(hex, 16);
  return [(value >> 16) & CHANNEL_MAX, (value >> 8) & CHANNEL_MAX, value & CHANNEL_MAX];
}

/** Signed distance from a point to a rounded rectangle centred on the origin. */
export function roundedRectDistance(
  [x, y]: Point,
  halfWidth: number,
  halfHeight: number,
  radius: number,
): number {
  const qx = Math.abs(x) - (halfWidth - radius);
  const qy = Math.abs(y) - (halfHeight - radius);
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
  return outside + Math.min(Math.max(qx, qy), 0) - radius;
}

/** Distance from a point to the segment a–b. */
export function segmentDistance([px, py]: Point, [ax, ay]: Point, [bx, by]: Point): number {
  const dx = bx - ax;
  const dy = by - ay;
  const t = Math.min(Math.max(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0), 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** Distance from a point to the nearest piece of a polyline (a run of joined segments). */
export function polylineDistance(point: Point, polyline: readonly Point[]): number {
  let nearest = Number.POSITIVE_INFINITY;
  for (let index = 1; index < polyline.length; index += 1) {
    nearest = Math.min(nearest, segmentDistance(point, polyline[index - 1]!, polyline[index]!));
  }
  return nearest;
}

/** How much of a one-pixel-wide sample a shape covers, from its signed distance in pixels. */
export function coverage(distancePx: number): number {
  return Math.min(Math.max(0.5 - distancePx, 0), 1);
}

/** `under` with `over` laid on top at `amount` (0 to 1). */
export function blend(under: Rgb, over: Rgb, amount: number): Rgb {
  return [0, 1, 2].map((index) =>
    Math.round(under[index]! + (over[index]! - under[index]!) * amount),
  ) as unknown as Rgb;
}

/**
 * Draws an image as raw PNG scanlines (a filter byte, then RGBA per pixel),
 * asking `shade` for each pixel's colour and opacity at its centre.
 */
export function drawScanlines(
  width: number,
  height: number,
  shade: (point: Point) => readonly number[],
): Buffer {
  const rowBytes = 1 + width * BYTES_PER_PIXEL;
  const raw = Buffer.alloc(rowBytes * height);
  for (let row = 0; row < height; row += 1) {
    raw[row * rowBytes] = PNG_FILTER_NONE;
    for (let column = 0; column < width; column += 1) {
      raw.set(shade([column + 0.5, row + 0.5]), row * rowBytes + 1 + column * BYTES_PER_PIXEL);
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

/** Wraps RGBA scanlines in a PNG file. */
export function encodePng(width: number, height: number, scanlines: Buffer): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.writeUInt8(PNG_BIT_DEPTH, 8);
  header.writeUInt8(PNG_COLOUR_TYPE_RGBA, 9);
  return Buffer.concat([
    PNG_SIGNATURE,
    pngChunk('IHDR', header),
    pngChunk('IDAT', deflateSync(scanlines)),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}
