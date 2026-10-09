// @vitest-environment node
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * The home-screen files (manifest, icons, head tags) repeat a few colours and
 * paths that live elsewhere. These checks keep the copies in step.
 */

const FRONTEND_ROOT = new URL('../../', import.meta.url);
const PNG_WIDTH_OFFSET = 16;
const PNG_HEIGHT_OFFSET = 20;

function readText(path: string): string {
  return readFileSync(new URL(path, FRONTEND_ROOT), 'utf8');
}

interface ManifestIcon {
  src: string;
  sizes: string;
  purpose: string;
}

interface Manifest {
  name: string;
  short_name: string;
  display: string;
  start_url: string;
  background_color: string;
  theme_color: string;
  icons: ManifestIcon[];
}

const manifest = JSON.parse(readText('public/manifest.webmanifest')) as Manifest;
const html = readText('index.html');

/** The page background token, light theme first and dark second. */
function backgroundTokens(): string[] {
  return [...readText('src/theme/tokens.css').matchAll(/--tracker-bg:\s*(#[0-9a-f]{6});/gi)].map(
    (match) => match[1] ?? '',
  );
}

function pngSize(publicPath: string): string {
  const png = readFileSync(new URL(`public${publicPath}`, FRONTEND_ROOT));
  return `${png.readUInt32BE(PNG_WIDTH_OFFSET)}x${png.readUInt32BE(PNG_HEIGHT_OFFSET)}`;
}

function themeColour(scheme: 'light' | 'dark'): string | undefined {
  const tag = new RegExp(
    `<meta name="theme-color" media="\\(prefers-color-scheme: ${scheme}\\)" content="(#[0-9a-f]{6})"`,
    'i',
  );
  return tag.exec(html)?.[1];
}

describe('the home-screen install', () => {
  it('opens Threadline on its own, like an app', () => {
    expect(manifest).toMatchObject({
      name: 'Threadline',
      short_name: 'Threadline',
      display: 'standalone',
      start_url: '/',
    });
    expect(html).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
  });

  it('uses the page background colour of each theme', () => {
    const [light, dark] = backgroundTokens();
    expect(manifest.background_color).toBe(light);
    expect(manifest.theme_color).toBe(light);
    expect(themeColour('light')).toBe(light);
    expect(themeColour('dark')).toBe(dark);
  });

  it('points at icons of the sizes it claims', () => {
    for (const icon of manifest.icons) expect(pngSize(icon.src)).toBe(icon.sizes);
    expect(manifest.icons.map((icon) => icon.purpose)).toContain('maskable');
    expect(html).toContain('href="/icons/apple-touch-icon-180.png"');
    expect(pngSize('/icons/apple-touch-icon-180.png')).toBe('180x180');
  });

  it('draws to the screen edges and keeps its controls clear of the notch and home bar', () => {
    expect(html).toContain('viewport-fit=cover');
    expect(readText('src/index.css')).toContain('env(safe-area-inset-left)');
    expect(readText('src/components/BottomNav.tsx')).toContain('env(safe-area-inset-bottom)');
  });

  it('is allowed by the content security policy', () => {
    expect(readText('vercel.json')).toContain("manifest-src 'self'");
  });
});
