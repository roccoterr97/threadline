/**
 * Draws the picture link previews show for the public demo (Open Graph and
 * X cards): 1200×630, the logo mark beside a sketch of the people list, in
 * the design tokens' colours. It holds no words; the preview's title and
 * description come from the page's meta tags.
 *
 * Run with `npm run social-card` after changing the mark or the palette, and
 * commit the file it writes. Only the demo build publishes it.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { MARK, markDistance } from './logoMark.ts';
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

const SOCIAL_CARD_FILE = new URL('../assets/social-card.png', import.meta.url);
const WIDTH = 1200;
const HEIGHT = 630;

/** A rounded box: centre, half sizes and corner radius, in pixels. */
interface Box {
  centre: Point;
  half: Point;
  radius: number;
}

/** One coloured shape, painted over whatever is below it. */
interface Layer {
  distance: (pixel: Point) => number;
  colour: Rgb;
}

function box(left: number, top: number, width: number, height: number, radius: number): Box {
  return { centre: [left + width / 2, top + height / 2], half: [width / 2, height / 2], radius };
}

function boxLayer({ centre, half, radius }: Box, colour: Rgb): Layer {
  return {
    distance: ([x, y]) => roundedRectDistance([x - centre[0], y - centre[1]], half[0], half[1], radius),
    colour,
  };
}

const MARK_LEFT = 130;
const MARK_TOP = 195;
const MARK_SIZE = 240;

/** The app icon: the mark's strokes on an accent rounded square. */
function markLayers(accent: Rgb, mark: Rgb): Layer[] {
  const scale = MARK_SIZE / MARK.box;
  return [
    boxLayer(box(MARK_LEFT, MARK_TOP, MARK_SIZE, MARK_SIZE, MARK.cornerRadius * scale), accent),
    {
      distance: ([x, y]) => markDistance([(x - MARK_LEFT) / scale, (y - MARK_TOP) / scale]) * scale,
      colour: mark,
    },
  ];
}

const PANEL = box(450, 120, 640, 390, 28);
const ROW_HEIGHT = 92;
const NAME_WIDTHS = [230, 180, 260, 200] as const;

/** One person in the sketched list: a category dot, a name, a status chip. */
function rowLayers(index: number, css: string, line: Rgb, ink: Rgb): Layer[] {
  const top = 140 + index * ROW_HEIGHT;
  const middle = top + ROW_HEIGHT / 2;
  const hue = (['violet', 'cyan', 'orange', 'teal'] as const)[index] ?? 'violet';
  const chip = (['positive', 'warn', 'neutral', 'positive'] as const)[index] ?? 'neutral';
  const layers: Layer[] = [
    boxLayer(box(500, middle - 11, 22, 22, 11), readToken(css, `tracker-category-${hue}-text`)),
    boxLayer(box(545, middle - 22, NAME_WIDTHS[index] ?? 200, 18, 9), ink),
    boxLayer(box(545, middle + 8, 140, 12, 6), line),
    boxLayer(box(890, middle - 20, 160, 40, 20), readToken(css, `tracker-${chip}-soft`)),
    boxLayer(box(915, middle - 6, 110, 12, 6), readToken(css, `tracker-${chip}-text`)),
  ];
  if (index > 0) layers.unshift(boxLayer(box(470, top, 600, 2, 1), line));
  return layers;
}

function layers(css: string): Layer[] {
  const line = readToken(css, 'tracker-border');
  const ink = readToken(css, 'tracker-text');
  return [
    ...markLayers(readToken(css, 'tracker-accent'), readToken(css, 'tracker-accent-fg')),
    boxLayer({ ...PANEL, half: [PANEL.half[0] + 2, PANEL.half[1] + 2], radius: PANEL.radius + 2 }, line),
    boxLayer(PANEL, readToken(css, 'tracker-surface')),
    ...[0, 1, 2, 3].flatMap((index) => rowLayers(index, css, line, ink)),
  ];
}

function main(): void {
  const css = readTokens();
  const background = readToken(css, 'tracker-bg');
  const stack = layers(css);
  const scanlines = drawScanlines(WIDTH, HEIGHT, (pixel) => {
    const colour = stack.reduce<Rgb>(
      (under, layer) => blend(under, layer.colour, coverage(layer.distance(pixel))),
      background,
    );
    return [...colour, CHANNEL_MAX];
  });
  mkdirSync(new URL('./', SOCIAL_CARD_FILE), { recursive: true });
  writeFileSync(SOCIAL_CARD_FILE, encodePng(WIDTH, HEIGHT, scanlines));
}

main();
