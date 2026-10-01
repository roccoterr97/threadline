// @vitest-environment node
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CATEGORY_COLOURS } from '../domain/categorySettings';

/**
 * jsdom cannot measure colours, so the category palette is checked here
 * against the values in `tokens.css`: readable in both themes, and no two
 * slots so alike that two categories look the same.
 */

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
const darkStart = css.indexOf('@media (prefers-color-scheme: dark)');
const THEMES = { light: css.slice(0, darkStart), dark: css.slice(darkStart) } as const;

/** WCAG's minimum for body text. */
const MIN_TEXT_CONTRAST = 4.5;
/** Smallest OKLab distance (×100) allowed between two slots' text colours; 2 is "just noticeable". */
const MIN_SLOT_DISTANCE = 8;

type Rgb = [number, number, number];

function token(block: string, name: string): Rgb {
  const hex = new RegExp(`--${name}:\\s*#([0-9a-f]{6});`, 'i').exec(block)?.[1];
  if (hex === undefined) throw new Error(`--${name} is missing`);
  return [0, 2, 4].map((at) => Number.parseInt(hex.slice(at, at + 2), 16) / 255) as Rgb;
}

const linear = (channel: number) =>
  channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;

function luminance(colour: Rgb): number {
  const [r, g, b] = colour.map(linear) as Rgb;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

function oklab(colour: Rgb): Rgb {
  const [r, g, b] = colour.map(linear) as Rgb;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function distance(a: Rgb, b: Rgb): number {
  const [p, q] = [oklab(a), oklab(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) * 100;
}

/** A slot's text and soft background; grey reuses the neutral tokens. */
function slot(block: string, colour: string): { text: Rgb; soft: Rgb } {
  const prefix = colour === 'grey' ? 'tracker-neutral' : `tracker-category-${colour}`;
  return { text: token(block, `${prefix}-text`), soft: token(block, `${prefix}-soft`) };
}

describe.each(Object.entries(THEMES))('the category palette, %s theme', (_theme, block) => {
  const surface = token(block, 'tracker-surface');

  it.each(CATEGORY_COLOURS)('keeps %s text readable on its chip and on the page', (colour) => {
    const { text, soft } = slot(block, colour);
    expect(contrast(text, soft)).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
    expect(contrast(text, surface)).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
  });

  it('never has two slots that look alike', () => {
    const closest = CATEGORY_COLOURS.flatMap((a, index) =>
      CATEGORY_COLOURS.slice(index + 1).map((b) => ({
        pair: `${a}/${b}`,
        apart: distance(slot(block, a).text, slot(block, b).text),
      })),
    ).sort((x, y) => x.apart - y.apart)[0];
    expect(closest?.apart, closest?.pair).toBeGreaterThanOrEqual(MIN_SLOT_DISTANCE);
  });
});
