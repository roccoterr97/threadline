import { OPERATIONS_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { DOCTOR_COMMAND, SETUP_COMMAND } from './commands';

/**
 * Mirrors part 7 of docs/setup-your-accounts.md, "The final check": the last
 * screen of the set-up and the doctor command that repeats its check.
 */
export const FINAL_CHECK: SetupPart = {
  id: 'final-check',
  title: 'The final check',
  summary:
    'The last screen names your personal link and the e-mail that signs in; one command repeats its check any time.',
  steps: [
    {
      id: 'set-up-done',
      title: 'Set-up done',
      intro: [
        {
          kind: 'paragraph',
          text: 'Just before the end, the set-up asks once `Connect LinkedIn now? It works if your LinkedIn profile is located in the EEA or Switzerland (about 5 minutes)`. Type `y` to connect it now (the LinkedIn part shows every click), or press Enter to leave it for later. A LinkedIn problem never undoes the rest.',
        },
        {
          kind: 'paragraph',
          text: 'The set-up ends by saying `Set-up done.`, then your dashboard\'s personal link and the e-mail address that can sign in to it (`Sign in there with …`). It then says how the first run was left (and, when it was started and an e-mail can be sent, when the first summary e-mail will arrive) and the daily time. Then it lists what was chosen for you, one line each with the command that changes it (`What was chosen, and the command that changes each:`), and how to add the extras. Then it checks every connection once and prints one line for each. The technical details of the whole set-up are in `backend/setup.log`, if anyone helping you needs them.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Write down the personal link and the e-mail address after `Sign in there with …`.',
            'Read the one line per connection that follows.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `Set-up done.`, your personal link, `Sign in there with …` and your address, then one line per connection.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If the set-up stopped before this screen, the line where it stopped says what to do; the next step repeats the check on its own.',
        },
      ],
    },
    {
      id: 'doctor',
      title: 'Check every connection yourself',
      command: DOCTOR_COMMAND,
      intro: [
        {
          kind: 'paragraph',
          text: 'You can run the same check yourself at any time, from the `backend` folder.',
        },
      ],
      youDo: [
        {
          kind: 'command',
          command: DOCTOR_COMMAND,
          what: 'Checks every account and setting, one line each.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The last line says `Everything Threadline needs is working.` Lines start with `ok`, or with `skipped` or `warning` for the optional parts. Until you add the extras, these are expected:',
        },
        {
          kind: 'bullets',
          items: [
            '`skipped  LinkedIn …: LinkedIn is not connected (optional)`',
            '`warning  Refresh now: not switched on yet (optional)`',
            '`warning  On-time morning start: not switched on (optional): GitHub alone starts the daily run, often late`',
          ],
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `Fix the lines marked \`PROBLEM\` from top to bottom. Each one ends with the command that repairs it, usually \`${SETUP_COMMAND}\` followed by the step's name.`,
        },
        {
          kind: 'paragraph',
          text: `You are done. You can now delete the Supabase key named \`threadline-setup-…\` (or the token you pasted) under **Account → Access Tokens** on Supabase. From now on, [operations.md](${OPERATIONS_URL}) is the page to keep: what happens every morning, and what to do when the summary asks for something.`,
        },
      ],
    },
  ],
};
