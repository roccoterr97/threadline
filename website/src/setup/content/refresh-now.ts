import { REFRESH_NOW_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { SUPABASE_TOKENS_PAGE } from './addresses';
import { STEP_COMMAND } from './commands';

/**
 * Mirrors part 8b of docs/setup-your-accounts.md, "Refresh now": the
 * dashboard's Refresh now button and the on-time morning start, switched on
 * with one GitHub key and one Supabase token.
 */
export const REFRESH_NOW: SetupPart = {
  id: 'refresh-now',
  title: 'Refresh now',
  summary:
    'The dashboard\'s Refresh now button, and the on-time morning start that makes the daily run begin at your time.',
  intro: [
    {
      kind: 'paragraph',
      text: 'The dashboard\'s **Refresh now** button starts one extra, quick update whenever you want: it reads only what is new and sends no e-mail. This step switches it on, together with the **on-time morning start**. It puts a small helper called `refresh-now` into your Supabase project. You install nothing: the set-up does it through Supabase\'s and GitHub\'s websites. It needs two keys, each pasted once (nothing shows while you paste) and never saved on your computer.',
    },
    {
      kind: 'paragraph',
      text: '**Before you start:** the dashboard is published and your private copy is on GitHub. If not, the set-up says which step to run first. Only a private repository you administer counts as your copy: if this folder still points at the public template, the set-up says `This folder is not linked to your own private copy on GitHub yet` and stops before anything is made. Without the GitHub tool it cannot check this, so it names the repository it will use and asks you to confirm it.',
    },
  ],
  steps: [
    {
      id: 'refresh-now-keys',
      title: 'Switch it on with two keys',
      command: STEP_COMMAND.refresh,
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'The set-up then saves the helper\'s settings in Supabase (your GitHub key goes straight there), puts the helper in place, and checks that it answers.',
        },
        {
          kind: 'paragraph',
          text: 'Last, it switches on the **on-time morning start**. GitHub often starts the daily run hours after the time you chose; now your Supabase project checks every 15 minutes and starts it as soon as your time has passed, at most once a day. GitHub\'s own schedule stays as a backup and stops by itself when the day\'s run already started. It is free and needs nothing more from you.',
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: 'Answer **yes** to `Switch on Refresh now for …?` (press Enter), then make the two keys.',
        },
        {
          kind: 'paragraph',
          text: '**1. The GitHub key.** A GitHub page opens with the name (`Threadline refresh now`), a one-year expiry date and the permission **Actions: Read and write** already filled in. Sign in if asked, then:',
        },
        {
          kind: 'steps',
          items: [
            'Under **Repository access**, choose **Only select repositories** and pick your copy of Threadline (the set-up names it, for example `your-name/threadline`). GitHub cannot fill this in for you.',
            'Click **Generate token** at the bottom and copy the token (it starts with `github_pat_`).',
            'Paste it into the set-up. It checks the key can see your workflow, without starting anything.',
          ],
        },
        {
          kind: 'note',
          text: `Put the expiry date in your calendar: on that day the button stops working until you run \`${STEP_COMMAND.refresh}\` again with a new key.`,
        },
        {
          kind: 'paragraph',
          text: `**2. The Supabase token.** The set-up asks for a Supabase access token once more, because it never saved the one from the Supabase part. Make one exactly as there, on [supabase.com/dashboard/account/tokens](${SUPABASE_TOKENS_PAGE}): **Generate new token**, then the small link **Create legacy token**, a name, the shortest expiry, **Generate token**. Or paste the one from the Supabase part if you still have it.`,
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The set-up says `Refresh now is switched on` and ends with `On-time morning start is switched on: Supabase starts the daily run at …` with your time. Open your dashboard and press **Refresh now** (on a phone: **Refresh**): the line under the header says "Refreshing… new messages will appear in a few minutes."',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '`GitHub did not accept the token` or `the token cannot see the workflow`: make the key again and check that step 1 picked your copy of Threadline and that **Actions** says **Read and write**.',
            '`Supabase did not accept the access token` or `Supabase says this access token has too little access`: make the Supabase token again with the **Create legacy token** link, as in the Supabase part.',
            '`The workflow is switched off on GitHub`: open the link the set-up shows and click **Enable workflow**.',
            'The dashboard still says "not switched on yet": close the dashboard tab and open it again (it remembers that answer until the tab is closed).',
            `\`your database does not have the on-time morning start yet\`: run \`${STEP_COMMAND.database}\`, then \`${STEP_COMMAND.refresh}\` again.`,
            `Anything else: [the manual way](${REFRESH_NOW_URL}) does the same by hand.`,
          ],
        },
      ],
    },
  ],
};
