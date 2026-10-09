// @vitest-environment node
import { fileURLToPath } from 'node:url';
import { build, type Rollup } from 'vite';
import { describe, expect, it, vi } from 'vitest';
import { netlifyHeadersFile, netlifyRedirectsFile } from '../hosting/hostingRules';
import { DEMO_OWNER_EMAIL } from './demoData';

const FRONTEND_ROOT = fileURLToPath(new URL('../..', import.meta.url));
const BUILD_TIMEOUT_MS = 60_000;

interface Built {
  chunks: Array<{ name: string; code: string }>;
  /** Every other emitted file by name, with the text of the page itself. */
  assets: Map<string, string | Uint8Array>;
}

/** Builds the dashboard in memory and returns what it would write. */
async function buildInMemory(mode: string): Promise<Built> {
  const result = await build({
    root: FRONTEND_ROOT,
    mode,
    logLevel: 'silent',
    build: { write: false },
  });
  const outputs = (Array.isArray(result) ? result : [result]) as Rollup.RollupOutput[];
  const files = outputs.flatMap((output) => output.output);
  return {
    chunks: files
      .filter((item): item is Rollup.OutputChunk => item.type === 'chunk')
      .map((chunk) => ({ name: chunk.fileName, code: chunk.code })),
    assets: new Map(
      files
        .filter((item): item is Rollup.OutputAsset => item.type === 'asset')
        .map((asset) => [asset.fileName, asset.source]),
    ),
  };
}

const PNG_WIDTH_OFFSET = 16;
const PNG_HEIGHT_OFFSET = 20;

function pngSize(source: string | Uint8Array | undefined): string {
  if (!(source instanceof Uint8Array)) return 'missing';
  const view = new DataView(source.buffer, source.byteOffset, source.byteLength);
  return `${view.getUint32(PNG_WIDTH_OFFSET)}x${view.getUint32(PNG_HEIGHT_OFFSET)}`;
}

function page(built: Built): string {
  const html = built.assets.get('index.html');
  return typeof html === 'string' ? html : '';
}

function containsDemo(chunks: ReadonlyArray<{ name: string; code: string }>): boolean {
  return chunks.some(
    (chunk) => chunk.name.includes('startDemo') || chunk.code.includes(DEMO_OWNER_EMAIL),
  );
}

describe('the demo in built bundles', () => {
  it(
    'is left out of a normal production build, which stays unlisted and has no link preview',
    async () => {
      const built = await buildInMemory('production');
      expect(containsDemo(built.chunks)).toBe(false);
      expect(page(built)).toContain('<meta name="robots" content="noindex, nofollow" />');
      expect(page(built)).not.toMatch(/og:|twitter:/);
      expect(built.assets.has('social-card.png')).toBe(false);
    },
    BUILD_TIMEOUT_MS,
  );

  it(
    'loads config.js only when no settings are compiled in, and never ships one',
    async () => {
      // The test set-up compiles in stand-in settings, like a Vercel project.
      const compiled = await buildInMemory('production');
      expect(page(compiled)).not.toContain('config.js');
      expect(compiled.assets.has('_headers')).toBe(false);

      // The prebuilt release is built with none, like the release workflow.
      vi.stubEnv('VITE_SUPABASE_URL', '');
      vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
      const prebuilt = await buildInMemory('production');
      vi.unstubAllEnvs();
      const html = page(prebuilt);
      expect(html).toContain('<script src="/config.js"></script>');
      expect(html.indexOf('/config.js')).toBeLessThan(html.indexOf('type="module"'));
      expect(prebuilt.assets.has('config.js')).toBe(false);
      expect(prebuilt.assets.get('_headers')).toBe(netlifyHeadersFile());
      expect(prebuilt.assets.get('_redirects')).toBe(netlifyRedirectsFile());
    },
    BUILD_TIMEOUT_MS * 2,
  );

  it(
    'is present in a demo build, with the link preview tags and picture',
    async () => {
      const built = await buildInMemory('demo');
      expect(containsDemo(built.chunks)).toBe(true);
      expect(page(built)).not.toContain('noindex');
      expect(page(built)).not.toContain('config.js');
      for (const tag of ['og:title', 'og:description', 'og:image', 'twitter:card']) {
        expect(page(built)).toContain(tag);
      }
      expect(page(built)).toContain('<meta name="twitter:card" content="summary_large_image" />');
      expect(pngSize(built.assets.get('social-card.png'))).toBe('1200x630');
    },
    BUILD_TIMEOUT_MS,
  );
});
