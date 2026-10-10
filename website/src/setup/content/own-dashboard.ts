import { NETLIFY_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { STEP_COMMAND } from './commands';

/**
 * Mirrors part 8d of docs/setup-your-accounts.md, "Your own dashboard on
 * Netlify": publishing an own copy instead of using the shared dashboard,
 * and the one thing Netlify makes you do by hand when it keeps a new site
 * private. The step ids are the ones these steps had in the main set-up, so
 * a reader's saved ticks and open pages still find them.
 */
export const OWN_DASHBOARD: SetupPart = {
  id: 'own-dashboard',
  title: 'Your own dashboard on Netlify',
  summary:
    'Only if you would rather not use the shared dashboard: your own copy, at your own address, on a free Netlify account.',
  intro: [
    {
      kind: 'paragraph',
      text: 'The set-up publishes your own copy of the dashboard on Netlify, for free, at an address such as `https://threadline-xxxxxx.netlify.app`. You need a free Netlify account and one Netlify token.',
    },
  ],
  steps: [
    {
      id: 'netlify-token',
      title: 'Publish it with a Netlify token',
      command: STEP_COMMAND.dashboard,
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it downloads the ready-made dashboard, adds your project\'s address and its public key, and publishes it. It saves the address so the morning e-mail links to it, and points Supabase\'s sign-in link at it. Netlify\'s free plan is enough.',
        },
        {
          kind: 'bullets',
          items: [
            'The GitHub command-line tool must be signed in, because the set-up uses it to check who built the download. If it is not, the step prints `Run \'gh auth login\'`: do that, then run the step again.',
            'Before publishing, the step checks that the download was built by this project\'s own release workflow (a build attestation). If the check fails, **nothing is published**. When Node.js 22 or newer is installed, the step then offers to build the dashboard on your computer instead; answer yes.',
            'The dashboard\'s security settings (its security headers and its redirect rule) come from the set-up itself and never from the download.',
          ],
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Run the command above. When it asks which dashboard to use, choose your own copy on Netlify.',
            `It asks whether you already have a Netlify account. If not, answer **n**: [Netlify](${NETLIFY_URL})'s sign-up page opens. **Sign up with GitHub** is quickest. If Netlify answers "Email address is invalid", your GitHub e-mail address has a "+" in it, which Netlify refuses: use **Sign up with email** instead. Press Enter in the terminal once you are signed in.`,
            'Netlify\'s token page opens. Click **New access token**, name it `Threadline set-up`, choose the shortest expiry offered, click **Generate token** and copy it. The page may look slightly different.',
            'Paste the token into the terminal. It stays hidden and is never saved.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'On your phone, open the new address, type your e-mail, and click the link in the e-mail Supabase sends. Your dashboard opens.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            'If the set-up says Netlify keeps your dashboard private, do the next step.',
            'The sign-in messages are the same as in the dashboard part of the set-up.',
            `If the step warns that the downloaded dashboard is **newer than your copy of Threadline**, publish it from your own copy instead: run \`${STEP_COMMAND.dashboard} --build-here\` (this needs Node.js 22 or newer).`,
            'If you set `NETLIFY_SITE_ID` in `.env` yourself, it must be a Netlify site ID or a plain site name, nothing else.',
            `Your own copy stays as it was when it was published. To publish a newer one, run \`${STEP_COMMAND.dashboard}\` again.`,
          ],
        },
      ],
    },
    {
      id: 'make-it-public',
      title: 'If Netlify keeps your dashboard private',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'Only if the set-up stopped with `Netlify published your dashboard but keeps it private`. Netlify accounts made since July 2026 keep every new site private, so your phone cannot open it. Netlify gives the set-up no way to change that, so you do it once.',
        },
        {
          kind: 'note',
          text: 'This is safe: the dashboard has its own sign-in, and only your e-mail address can open your data.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Open your project (`threadline-xxxxxx`) on Netlify if it is not open already.',
            'Click **Project configuration → General → Visitor access**.',
            'Under **Project visibility**, click **Edit visibility**. If Netlify asks, choose **Customize this project\'s visibility**.',
            'Set **Production** to **Public** (leave the previews as they are) and click **Save**.',
            `Run \`${STEP_COMMAND.dashboard}\` again.`,
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The step now says `Check: https://threadline-xxxxxx.netlify.app opens the dashboard.`',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If Netlify does not offer **Public**, your team is set to keep every project private: change it in **Team settings → General → Visitor access → Default project visibility**, then do the steps above again.',
        },
      ],
    },
  ],
};
