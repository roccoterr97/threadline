import type { ClaudeWay, SetupGuide, SetupPart } from '../../setup/types';

/**
 * A small guide in the real shape, for the screens' tests. It has every kind
 * of block, a step for one computer only, an optional step and two extras.
 */

const BEFORE_YOU_START: SetupPart = {
  id: 'before-you-start',
  title: 'Before you start',
  summary: 'What you need on hand.',
  steps: [
    {
      id: 'have-accounts',
      title: 'Have your accounts ready',
      minutes: 5,
      intro: [{ kind: 'paragraph', text: 'You need **three** accounts.' }],
      youDo: [{ kind: 'bullets', items: ['GitHub', 'Supabase', 'Netlify'] }],
      check: [{ kind: 'paragraph', text: 'You can sign in to each one.' }],
      ifNot: [{ kind: 'paragraph', text: 'Make the missing one first.' }],
    },
  ],
};

const INSTALL: SetupPart = {
  id: 'install',
  title: 'Install',
  summary: 'Put Threadline on your computer.',
  intro: [{ kind: 'note', text: 'Open a terminal first.' }],
  steps: [
    {
      id: 'open-terminal',
      title: 'Open a terminal',
      minutes: 1,
      intro: [{ kind: 'paragraph', text: 'The terminal is where the set-up runs.' }],
      youDo: [
        { kind: 'steps', items: ['Press ⌘ + Space.'], platforms: ['mac'] },
        { kind: 'steps', items: ['Open the Start menu.'], platforms: ['windows'] },
        { kind: 'command', command: 'open -a Terminal', platforms: ['mac'], what: 'the Mac line' },
        { kind: 'command', command: 'start powershell', platforms: ['windows'], what: 'the Windows line' },
        { kind: 'command', command: 'gnome-terminal', platforms: ['linux'], what: 'the Linux line' },
      ],
      check: [{ kind: 'paragraph', text: 'A window with a blinking cursor.' }],
      ifNot: [{ kind: 'paragraph', text: 'Search your computer for "terminal".' }],
    },
    {
      id: 'run-install',
      title: 'Run the install line',
      command: 'tracker setup',
      minutes: 3,
      intro: [{ kind: 'paragraph', text: 'It downloads everything it needs.' }],
      youDo: [{ kind: 'steps', items: ['Paste the line', 'Press Enter'] }],
      check: [{ kind: 'value', value: 'Threadline is installed', what: 'the success line' }],
      ifNot: [{ kind: 'warning', text: 'Do not run it twice at once.' }],
    },
    {
      id: 'allow-windows',
      title: 'Allow the script on Windows',
      platforms: ['windows'],
      optional: true,
      intro: [{ kind: 'paragraph', text: 'Windows may ask first.' }],
      youDo: [{ kind: 'paragraph', text: 'Choose **Yes**.' }],
      check: [{ kind: 'paragraph', text: 'The install carries on.' }],
      ifNot: [
        {
          kind: 'table',
          rows: [
            ['What it says', 'What to do'],
            ['Blocked', 'Run it as an administrator'],
          ],
        },
      ],
    },
  ],
};

const FINAL_CHECK: SetupPart = {
  id: 'final-check',
  title: 'Final check',
  summary: 'Make sure the first run worked.',
  steps: [
    {
      id: 'first-run',
      title: 'Run it once',
      intro: [{ kind: 'paragraph', text: 'One run, by hand.' }],
      youDo: [{ kind: 'command', command: 'tracker run', what: 'the run line' }],
      check: [{ kind: 'paragraph', text: 'An e-mail arrives.' }],
      ifNot: [{ kind: 'paragraph', text: 'Look in [the operations guide](https://example.com/ops).' }],
    },
  ],
};

const LINKEDIN: SetupPart = {
  id: 'linkedin',
  title: 'LinkedIn',
  summary: 'Read your LinkedIn messages too.',
  steps: [
    {
      id: 'linkedin-sign-in',
      title: 'Sign in to LinkedIn once',
      intro: [{ kind: 'paragraph', text: 'A browser window opens.' }],
      youDo: [{ kind: 'paragraph', text: 'Sign in as usual.' }],
      check: [{ kind: 'paragraph', text: 'The window closes by itself.' }],
      ifNot: [{ kind: 'paragraph', text: 'Try again.' }],
    },
  ],
};

const REFRESH_NOW: SetupPart = {
  id: 'refresh-now',
  title: 'Refresh now',
  summary: 'A button on the dashboard that runs it at once.',
  steps: [
    {
      id: 'refresh-token',
      title: 'Make the refresh token',
      intro: [{ kind: 'paragraph', text: 'One token, kept in the dashboard.' }],
      youDo: [{ kind: 'paragraph', text: 'Run the command.' }],
      check: [{ kind: 'paragraph', text: 'The button appears.' }],
      ifNot: [{ kind: 'paragraph', text: 'Reload the dashboard.' }],
    },
  ],
};

export const FIXTURE_GUIDE: SetupGuide = {
  core: [BEFORE_YOU_START, INSTALL, FINAL_CHECK],
  extras: [LINKEDIN, REFRESH_NOW],
};

export const FIXTURE_CLAUDE_WAY: ClaudeWay = {
  title: 'Let Claude do it',
  summary: 'Paste one text into the Claude app and answer its questions.',
  intro: [{ kind: 'paragraph', text: 'Claude runs the terminal for you.' }],
  prompt: 'Set up Threadline for me from https://example.com/setup-with-claude',
  afterwards: [{ kind: 'steps', items: ['Claude installs it', 'Claude asks for your accounts'] }],
};
