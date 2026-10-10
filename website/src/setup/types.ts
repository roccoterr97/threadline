import type { Platform } from '../lib/platform';

/**
 * The shape of the guided set-up's content. The content files under
 * `./content/` are plain data in this shape; the screens under `../pages/`
 * draw it. Keeping the two apart lets the words be checked and changed
 * without touching a component.
 *
 * Text fields accept a little inline markup, rendered by `InlineText`:
 *   **bold**, `code`, and [a link](https://…).
 */

/** Shown only for the listed computers; every computer when omitted. */
export interface ForPlatforms {
  platforms?: readonly Platform[];
}

/**
 * One piece of a step's content. The kinds that carry words (`paragraph`,
 * `steps`, `bullets`, `note`, `warning`) and `command` can be limited to some
 * computers, so a reader only sees the sentences for their own.
 */
export type Block =
  | ({ kind: 'paragraph'; text: string } & ForPlatforms)
  /** A line to paste into a terminal, with a copy button. */
  | ({ kind: 'command'; command: string; what: string } & ForPlatforms)
  /** Numbered actions, in order. */
  | ({ kind: 'steps'; items: readonly string[] } & ForPlatforms)
  | ({ kind: 'bullets'; items: readonly string[] } & ForPlatforms)
  /** A value to copy as it is (an address, a name), with a copy button. */
  | { kind: 'value'; value: string; what: string }
  | ({ kind: 'note'; text: string } & ForPlatforms)
  | ({ kind: 'warning'; text: string } & ForPlatforms)
  /** A two-column table, first row being the header. */
  | { kind: 'table'; rows: readonly (readonly [string, string])[] };

/** Whether a block is meant for this computer: every block is, unless it lists others. */
export function isForPlatform(block: Block, platform: Platform): boolean {
  if (!('platforms' in block) || block.platforms === undefined) return true;
  return block.platforms.includes(platform);
}

/** One of the answers a part can ask for before showing its steps. */
export interface ChoiceOption {
  id: string;
  label: string;
}

/** A question a part asks first ("Which mailbox?"), so only the matching steps show. */
export interface PartChoice {
  /** Stable; the answer is remembered under it. */
  id: string;
  question: string;
  options: readonly ChoiceOption[];
}

/** One thing the reader does, with what to look for afterwards. */
export interface SetupStep {
  /** Stable, unique across the whole guide; progress is remembered by it. */
  id: string;
  title: string;
  /** The terminal command that runs this step on its own, when there is one. */
  command?: string;
  /** Roughly how long it takes, in minutes of the reader's own time. */
  minutes?: number;
  /** Only shown for these computers; every computer when omitted. */
  platforms?: readonly Platform[];
  optional?: boolean;
  /** Only shown when the part's choice is one of these options; shown while no choice is made yet. */
  onlyFor?: readonly string[];
  /** Why this step exists and what happens, before the reader does anything. */
  intro: readonly Block[];
  /** What the reader does. */
  youDo: readonly Block[];
  /** What the reader should see when it worked. */
  check: readonly Block[];
  /** What to do when the check fails. */
  ifNot: readonly Block[];
}

/** A group of steps with one purpose, shown on one page. */
export interface SetupPart {
  /** Stable and unique; it is the page's address under `/setup/`. */
  id: string;
  title: string;
  /** One sentence for the list of parts. */
  summary: string;
  /** Shown above the steps. */
  intro?: readonly Block[];
  /** A question asked before the steps, which narrows them down. */
  choice?: PartChoice;
  steps: readonly SetupStep[];
}

/** The whole guided set-up: the parts everyone does, then the extras. */
export interface SetupGuide {
  /** The parts the first morning e-mail needs, in order. */
  core: readonly SetupPart[];
  /** Optional parts, any time after the core: LinkedIn, Refresh now, the cloud route, an own dashboard. */
  extras: readonly SetupPart[];
}

/** The other way in: one sentence pasted into the Claude app, which then does the terminal work. */
export interface ClaudeWay {
  title: string;
  summary: string;
  /** What to expect, before pasting. */
  intro: readonly Block[];
  /** The exact text to paste into the Claude app. */
  prompt: string;
  /** What Claude then takes the reader through, in order. */
  afterwards: readonly Block[];
}
