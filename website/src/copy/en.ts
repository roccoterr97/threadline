/**
 * The words of the website's frame: menus, buttons and small labels. Long
 * page content lives in `src/content/` and `src/setup/content/`.
 *
 * House rules: plain English, no jargon, no abbreviations. A button says what
 * happens when it is pressed.
 */

export const site = {
  name: 'Threadline',
  tagline: 'Every conversation, one clear line.',
  skipToContent: 'Skip to the main content',
  loading: 'Loading…',
} as const;

export const nav = {
  label: 'Main menu',
  home: 'Home',
  questions: 'Questions',
  privacy: 'Privacy',
  support: 'Support',
  setup: 'Set it up',
  dashboard: 'Your dashboard',
  demo: 'Try the demo',
  update: 'Update',
  github: 'GitHub',
} as const;

export const footer = {
  label: 'More',
  madeWith: 'Free and open source, MIT licence.',
  privacy: 'Everything runs on accounts you own. Nothing is sent to us.',
  independent:
    'Threadline is an independent project. It is not made by, or affiliated with, Anthropic, LinkedIn, Microsoft or Google.',
  guide: 'Full written guide',
  operations: 'When something fails',
  security: 'Security',
  licence: 'Licence',
  changelog: 'What changed',
  issues: 'Report a problem',
} as const;

export const copyButton = {
  copy: 'Copy',
  copied: 'Copied',
  failed: 'Select and copy it by hand',
  label: (what: string) => `Copy ${what}`,
} as const;

export const callout = {
  check: 'Check',
  ifNot: 'If not',
  note: 'Good to know',
  warning: 'Careful',
} as const;

export const platform = {
  label: 'Your computer',
} as const;

export const notFound = {
  title: 'There is nothing at this address',
  body: 'The page may have moved. Start again from the home page.',
  home: 'Go to the home page',
} as const;

export const onThisPage = 'On this page';

export const questionsPage = {
  title: 'Questions',
  lead: 'Short answers to what people ask most.',
  missing: 'Something missing? Write to',
  orGitHub: 'or ask on GitHub',
  stillDeciding: 'Still deciding? Try the demo: the real dashboard with made-up people, nothing to sign up for.',
} as const;

export const privacyPage = {
  title: 'Privacy',
  lead: 'This website does not track you, and Threadline runs on your own accounts, so we never see your data.',
  asOf: 'October 2026',
} as const;

export const wizard = {
  title: 'Set it up',
  lead: 'About 20 minutes with GitHub and Supabase ready, about 30 without. One step per screen. Your place is remembered in this browser.',
  needs: [
    'A Mac, Windows or Linux computer',
    'A paid Claude plan (Pro, Max or Team)',
    'Free GitHub and Supabase accounts',
    'The mailbox you want it to read',
  ],
  start: 'Start',
  continue: 'Continue where I left off',
  claudeInstead: 'Prefer to let Claude do it?',
  extrasTitle: 'Extras, any time after',
  startAgain: 'Start again from the beginning',
  confirmStartAgain: 'Forget every finished step and start again?',

  computerQuestion: 'Which computer are you setting it up on?',
  wayQuestion: 'How do you want to do it?',
  wayByHand: 'Step by step, by hand',
  wayByHandHint: 'This guide walks you through it. You paste a few lines and click where it says.',
  wayClaude: 'Let Claude do it',
  wayClaudeHint: 'You paste one sentence into the Claude app; it does the terminal work. Mac and Linux only.',

  back: 'Back',
  next: 'Next',
  doneNext: 'Done, next',
  skip: 'Skip this step',
  finish: 'Finish',
  toStart: 'Back to the start',
  stepOf: (number: number, total: number) => `Step ${number} of ${total}`,
  optional: 'Optional',
  youShouldSee: 'You should see',
  why: 'Why this step',
  didNotWork: 'Did it not work?',
  commandWhat: (title: string) => `the command for "${title}"`,
  promptWhat: 'the text to paste into Claude',
  promptLabel: 'Paste this into the Claude app',
  afterwards: 'What happens next',

  doneTitle: 'That is it.',
  doneBody: 'Your personal link to the dashboard and the e-mail that signs in are on the last screen of the set-up. The first morning e-mail arrives about ten minutes after the first run.',
  openDashboard: 'Go to your dashboard',
  noSuchScreen: 'There is no screen at this address',
  noSuchScreenBody: 'Start again from the beginning of the set-up.',
} as const;
