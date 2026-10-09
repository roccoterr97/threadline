import { describe, expect, it } from 'vitest';
import { INSTALL_LINE_MAC_LINUX, INSTALL_LINE_WINDOWS } from '../constants/links';
import { PLATFORMS } from '../lib/platform';
import { CLAUDE_WAY, SETUP_GUIDE } from './guide';
import type { Block, SetupPart, SetupStep } from './types';

/** A part or step id doubles as a page address, so it must be URL-safe. */
const URL_SAFE_ID = /^[a-z0-9-]+$/;
const LINK = /\[([^\]]*)\]\(([^)]*)\)/g;
/** Code spans may hold `<step>`-style placeholders; anything else must not. */
const CODE_SPAN = /`[^`]*`/g;
/** A sentence that names every computer at once; blocks carry `platforms` instead. */
const PER_COMPUTER_LABEL = /\*\*(Mac|Windows|Linux)( \(PowerShell\)| or Linux)?:\*\*/;

const ALL_PARTS: readonly SetupPart[] = [...SETUP_GUIDE.core, ...SETUP_GUIDE.extras];
const ALL_STEPS: readonly SetupStep[] = ALL_PARTS.flatMap((part) => part.steps);

/** Every piece of text a block shows, as one list. */
function textsOf(block: Block): readonly string[] {
  switch (block.kind) {
    case 'paragraph':
    case 'note':
    case 'warning':
      return [block.text];
    case 'command':
      return [block.command, block.what];
    case 'value':
      return [block.value, block.what];
    case 'steps':
    case 'bullets':
      return block.items;
    case 'table':
      return block.rows.flat();
  }
}

function blocksOfStep(step: SetupStep): readonly Block[] {
  return [...step.intro, ...step.youDo, ...step.check, ...step.ifNot];
}

const ALL_BLOCKS: readonly Block[] = [
  ...ALL_PARTS.flatMap((part) => part.intro ?? []),
  ...ALL_STEPS.flatMap(blocksOfStep),
  ...CLAUDE_WAY.intro,
  ...CLAUDE_WAY.afterwards,
];

const ALL_TEXTS: readonly string[] = [
  ...ALL_PARTS.flatMap((part) => [part.title, part.summary]),
  ...ALL_STEPS.map((step) => step.title),
  CLAUDE_WAY.title,
  CLAUDE_WAY.summary,
  CLAUDE_WAY.prompt,
  ...ALL_BLOCKS.flatMap(textsOf),
];

describe('the guided set-up content', () => {
  it('has the core parts in the order of the written guide', () => {
    expect(SETUP_GUIDE.core.map((part) => part.id)).toEqual([
      'before-you-start',
      'install',
      'supabase',
      'login-categories-time-zone',
      'mailbox',
      'dashboard',
      'github',
      'final-check',
    ]);
    expect(SETUP_GUIDE.extras.map((part) => part.id)).toEqual([
      'linkedin',
      'refresh-now',
      'cloud-route',
    ]);
  });

  it('gives every part and step a unique, URL-safe id', () => {
    const ids = [...ALL_PARTS.map((part) => part.id), ...ALL_STEPS.map((step) => step.id)];
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(URL_SAFE_ID);
  });

  it('leaves no title, summary or step section empty', () => {
    for (const part of ALL_PARTS) {
      expect(part.title.trim()).not.toBe('');
      expect(part.summary.trim()).not.toBe('');
      expect(part.steps.length).toBeGreaterThan(0);
      for (const step of part.steps) {
        expect(step.title.trim()).not.toBe('');
        expect(step.intro.length).toBeGreaterThan(0);
        expect(step.youDo.length).toBeGreaterThan(0);
        expect(step.check.length).toBeGreaterThan(0);
        expect(step.ifNot.length).toBeGreaterThan(0);
      }
    }
  });

  it('leaves no text empty', () => {
    for (const text of ALL_TEXTS) expect(text.trim()).not.toBe('');
  });

  it('says what every command and value block is for', () => {
    for (const block of ALL_BLOCKS) {
      if (block.kind !== 'command' && block.kind !== 'value') continue;
      expect(block.what.trim()).not.toBe('');
    }
  });

  it('links only to https addresses', () => {
    for (const text of ALL_TEXTS) {
      for (const match of text.matchAll(LINK)) {
        const label = match[1] ?? '';
        const address = match[2] ?? '';
        expect(label.trim()).not.toBe('');
        expect(address).toMatch(/^https:\/\//);
      }
    }
  });

  it('contains no raw HTML', () => {
    for (const text of ALL_TEXTS) {
      expect(text.replace(CODE_SPAN, '')).not.toContain('<');
    }
  });

  it('shows the install lines exactly as the constants', () => {
    const commands = ALL_BLOCKS.flatMap((block) =>
      block.kind === 'command' ? [block.command] : [],
    );
    expect(commands).toContain(INSTALL_LINE_MAC_LINUX);
    expect(commands).toContain(INSTALL_LINE_WINDOWS);
  });

  it('limits a block or step only to computers the set-up knows', () => {
    const scoped = [...ALL_BLOCKS, ...ALL_STEPS].flatMap((item) =>
      'platforms' in item && item.platforms !== undefined ? [item.platforms] : [],
    );
    expect(scoped.length).toBeGreaterThan(0);
    for (const platforms of scoped) {
      expect(platforms.length).toBeGreaterThan(0);
      for (const platform of platforms) expect(PLATFORMS).toContain(platform);
    }
  });

  it('never labels sentences per computer; the block is limited instead', () => {
    for (const text of ALL_TEXTS) expect(text).not.toMatch(PER_COMPUTER_LABEL);
  });

  it('gives the Claude way a prompt and what follows it', () => {
    expect(CLAUDE_WAY.prompt).toContain('Please set up Threadline for me.');
    expect(CLAUDE_WAY.intro.length).toBeGreaterThan(0);
    expect(CLAUDE_WAY.afterwards.length).toBeGreaterThan(0);
  });
});

describe('the questions parts ask first', () => {
  it('limits a step only to answers its part offers', () => {
    for (const part of ALL_PARTS) {
      const offered = new Set(part.choice?.options.map((option) => option.id) ?? []);
      for (const step of part.steps) {
        for (const answer of step.onlyFor ?? []) {
          expect(offered.has(answer), `${part.id}/${step.id} waits for an answer "${answer}" its part never offers`).toBe(true);
        }
      }
    }
  });

  it('offers each answer once, with a label', () => {
    for (const part of ALL_PARTS) {
      if (part.choice === undefined) continue;
      const ids = part.choice.options.map((option) => option.id);
      expect(new Set(ids).size).toBe(ids.length);
      expect(part.choice.question).not.toBe('');
      part.choice.options.forEach((option) => expect(option.label).not.toBe(''));
    }
  });
});
