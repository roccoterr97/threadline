// @vitest-environment node
import { fileURLToPath } from 'node:url';
import { build, type Rollup } from 'vite';
import { describe, expect, it } from 'vitest';
import { DEMO_OWNER_EMAIL } from './demoData';

const FRONTEND_ROOT = fileURLToPath(new URL('../..', import.meta.url));
const BUILD_TIMEOUT_MS = 60_000;

/** Builds the dashboard in memory and returns every emitted chunk's name and code. */
async function buildChunks(mode: string): Promise<Array<{ name: string; code: string }>> {
  const result = await build({
    root: FRONTEND_ROOT,
    mode,
    logLevel: 'silent',
    build: { write: false },
  });
  const outputs = (Array.isArray(result) ? result : [result]) as Rollup.RollupOutput[];
  return outputs
    .flatMap((output) => output.output)
    .filter((item): item is Rollup.OutputChunk => item.type === 'chunk')
    .map((chunk) => ({ name: chunk.fileName, code: chunk.code }));
}

function containsDemo(chunks: ReadonlyArray<{ name: string; code: string }>): boolean {
  return chunks.some(
    (chunk) => chunk.name.includes('startDemo') || chunk.code.includes(DEMO_OWNER_EMAIL),
  );
}

describe('the demo in built bundles', () => {
  it(
    'is left out of a normal production build',
    async () => {
      expect(containsDemo(await buildChunks('production'))).toBe(false);
    },
    BUILD_TIMEOUT_MS,
  );

  it(
    'is present in a demo build, so the check above can see it',
    async () => {
      expect(containsDemo(await buildChunks('demo'))).toBe(true);
    },
    BUILD_TIMEOUT_MS,
  );
});
