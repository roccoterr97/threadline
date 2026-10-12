import { OPERATIONS_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { DOCTOR_COMMAND, SETUP_COMMAND, STEP_COMMAND } from './commands';

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
          text: 'The set-up ends by saying `Set-up done.`, then your dashboard\'s personal link (`Your dashboard (keep this link; it is on your clipboard): …`), which it also opens in your browser, and the e-mail address that can sign in to it (`Sign in there with …`). It then says when the summary e-mail comes (`After the first one, the summary e-mail comes every day at 07:00 (…).`) and `If a run stops with a problem, GitHub e-mails you; \'uv run tracker doctor\' says why.` When the first run was not started, it says how to start it instead. Then it lists what was chosen for you, one line each with the command that changes it (`What was chosen, and the command that changes each:`), the line `LinkedIn can be added later: uv run tracker setup linkedin (about 5 minutes).` (unless LinkedIn is already connected), and how to add the other extras (`Extras any time: …`). Last, it reminds you that you can delete its Supabase access, then checks every connection once (`Final check of every connection:`) and prints one line for each. The technical details of the whole set-up are in `backend/setup.log`, if anyone helping you needs them.',
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
        {
          kind: 'paragraph',
          text: 'The line **Daily run on GitHub** looks at the newest daily run: `ok` while it is going (`a daily run is going: …`) or when it finished well. It says `skipped` when there is no daily run yet, when the GitHub tool is not signed in on this computer, or when the folder is not linked to your private copy.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `Fix the lines marked \`PROBLEM\` from top to bottom. Each one ends with the command that repairs it, usually \`${SETUP_COMMAND}\` followed by the step's name.`,
        },
        {
          kind: 'paragraph',
          text: `\`PROBLEM  Daily run on GitHub: the newest daily run stopped.\` gives the reason the run left and the run's page. When it is about the Claude key (Claude refused it), run \`${STEP_COMMAND.github}\` to make a new key.`,
        },
        {
          kind: 'paragraph',
          text: `You are done. You can now delete the Supabase key named \`threadline-setup-…\` (or the token you pasted) under **Account → Access Tokens** on Supabase. From now on, [operations.md](${OPERATIONS_URL}) is the page to keep: what happens every morning, and what to do when the summary asks for something.`,
        },
      ],
    },
  ],
};
