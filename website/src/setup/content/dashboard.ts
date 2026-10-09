import type { SetupPart } from '../types';
import { SETUP_COMMAND, STEP_COMMAND } from './commands';

/**
 * Mirrors part 5 of docs/setup-your-accounts.md, "The dashboard (Netlify)":
 * the Netlify token, the free address, and the one thing Netlify makes you
 * do by hand when it keeps a new site private. Set-up step 9 of 11.
 */
export const DASHBOARD: SetupPart = {
  id: 'dashboard',
  title: 'The dashboard (Netlify)',
  summary:
    'One Netlify token publishes the dashboard at a free address that opens on your phone; the sign-in link is pointed at it for you.',
  intro: [
    {
      kind: 'paragraph',
      text: 'The dashboard is a private web page. The set-up publishes it on Netlify, for free, so you can open it on your computer and your phone. You make one token on Netlify\'s website and paste it. Nothing needs installing.',
    },
  ],
  steps: [
    {
      id: 'netlify-token',
      title: 'The Netlify token',
      command: STEP_COMMAND.dashboard,
      intro: [
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it downloads the ready-made dashboard, adds your project\'s address and its public key, and publishes it at an address such as `https://threadline-xxxxxx.netlify.app`. It saves that address so the morning e-mail links to it, and points Supabase\'s sign-in link at it with the Supabase token from the Supabase part. Netlify\'s free plan is enough.',
        },
        {
          kind: 'paragraph',
          text: 'Three things happen behind the scenes that are good to know:',
        },
        {
          kind: 'bullets',
          items: [
            'The GitHub command-line tool must be signed in for the ready-made dashboard, because the set-up uses it to check who built the download. If it is not, the step prints `Run \'gh auth login\'`: do that, then run the step again.',
            'Before publishing, the step checks that the download was built by this project\'s own release workflow (GitHub keeps a signed record of that, called a build attestation). If the check fails, **nothing is published**. When Node.js 22 or newer is installed, the step then offers to build the dashboard on your computer instead; answer yes.',
            'The dashboard\'s security settings (its security headers and its redirect rule) come from the set-up itself and never from the download.',
          ],
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'When the set-up asks `Publish it on Netlify now?`, press Enter (yes).',
            'It asks whether you already have a Netlify account. If not, answer **n**: Netlify\'s sign-up page opens. Signing up with GitHub is quickest; if Netlify answers "Email address is invalid", use **Sign up with email** instead. Press Enter in the terminal once you are signed in.',
            'Netlify\'s token page opens. Click **New access token**, name it `Threadline set-up`, choose the shortest expiry offered, click **Generate token** and copy it. The page may look slightly different.',
            'Paste the token into the terminal. It stays hidden and is never saved.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'On your phone, open the address, type your e-mail, and click the link in the e-mail Supabase sends. The dashboard opens (it is empty until the first run).',
        },
        {
          kind: 'note',
          text: '**Put it on your home screen.** Open the address in your phone\'s browser. On an iPhone, tap **Share → Add to Home Screen**. On Android, tap **⋮ → Add to Home screen**. It then opens like an app.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '"This address cannot sign in" on the dashboard means you typed another address than your dashboard login: use the one you typed at the login step, usually your Supabase address.',
            '"Too many links were asked for" means waiting as long as it says.',
            'Supabase\'s own message "Email address not authorized" means the address is not the one of your Supabase account (see the login step).',
            `A link that opens \`localhost\` means the sign-in link was not connected: run \`${STEP_COMMAND.dashboard}\` again. Running it again keeps the sign-in addresses you already have in Supabase and adds the new one; it tells you which it did.`,
            'If the set-up says Netlify keeps your dashboard private, do the next step.',
          ],
        },
        {
          kind: 'paragraph',
          text: `If the step warns that the downloaded dashboard is **newer than your copy of Threadline**, the dashboard expects database changes your copy does not have yet, and it may show errors. The safe way out is to publish the dashboard from your own copy with a local build: run \`${STEP_COMMAND.dashboard} --build-here\` (this needs Node.js 22 or newer).`,
        },
        {
          kind: 'paragraph',
          text: 'If you set `NETLIFY_SITE_ID` in `.env` yourself, it must be a Netlify site ID or a plain site name, nothing else.',
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
          text: 'Only if the set-up stopped with `Netlify published your dashboard but keeps it private` (its technical name in `setup.log` is `dashboard_private`).',
        },
        {
          kind: 'paragraph',
          text: 'Netlify accounts made since July 2026 keep every new site private, so only you, signed in to Netlify, can open it, and your phone cannot. Netlify gives the set-up no way to change that, so the set-up stops, opens your project\'s page on Netlify and lists the clicks. You do them once.',
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
            'Open your project (`threadline-xxxxxx`) if it is not open already.',
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
    {
      id: 'not-on-netlify',
      title: 'Not on Netlify?',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'Only if you would rather publish the dashboard somewhere else. The steps after this one need the dashboard\'s address, so the set-up cannot go on without one.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Answer **n** to `Publish it on Netlify now?`. The set-up asks whether you publish it somewhere else instead.',
            'Answer **y** and paste its address: the set-up opens it once and saves it if it shows the dashboard.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The set-up accepts the address and carries on with the daily time.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `If you answer **n** to both, the set-up stops there with \`Stopped: the dashboard is not published yet - publish it first (part 5 of the guide).\`. Run \`${SETUP_COMMAND}\` again when you are ready: it skips what is already done and carries on from the dashboard. To publish the dashboard again later, run \`${STEP_COMMAND.dashboard}\`.`,
        },
      ],
    },
  ],
};
