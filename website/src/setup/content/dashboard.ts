import { SHARED_DASHBOARD_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { STEP_COMMAND } from './commands';

/**
 * Mirrors part 5 of docs/setup-your-accounts.md, "Your dashboard": the
 * shared dashboard, the personal link that opens the reader's own data, and
 * signing in on a phone. Set-up step 9 of 11. An own copy on Netlify is an
 * extra (`./own-dashboard.ts`).
 */
export const DASHBOARD: SetupPart = {
  id: 'dashboard',
  title: 'Your dashboard',
  summary:
    'The shared dashboard, and your personal link to it. Nothing to publish, no extra account.',
  intro: [
    {
      kind: 'paragraph',
      text: `The dashboard is the web page that shows your people and conversations. You use the shared dashboard at [app.threadlineapp.com](${SHARED_DASHBOARD_URL}). The page is the same for everyone. Your data stays in your own Supabase database, and only your e-mail address can sign in.`,
    },
  ],
  steps: [
    {
      id: 'personal-link',
      title: 'Your personal link',
      command: STEP_COMMAND.dashboard,
      intro: [
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it points Supabase\'s sign-in link at the shared dashboard and gives you your **personal link**. That link opens your own dashboard. It carries your database\'s public address, nothing secret. The set-up saves it, so every morning summary e-mail carries it too.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'When the set-up offers the shared dashboard, press Enter (yes).',
            'Write down the personal link it shows.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The set-up shows your personal link. It starts with `https://app.threadlineapp.com`.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `Run \`${STEP_COMMAND.dashboard}\` again. It keeps the sign-in addresses you already have in Supabase and adds the new one; it tells you which it did.`,
        },
      ],
    },
    {
      id: 'dashboard-on-your-phone',
      title: 'Open it on your phone',
      intro: [
        {
          kind: 'paragraph',
          text: 'On a new device you open your personal link once, then sign in with the link Supabase e-mails you. The personal link is also in every morning e-mail.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'On your phone, open your personal link.',
            'Type your e-mail and click the link in the e-mail Supabase sends.',
          ],
        },
        {
          kind: 'note',
          text: '**Put it on your home screen.** On an iPhone, tap **Share → Add to Home Screen**. On Android, tap **⋮ → Add to Home screen**. It then opens like an app.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The dashboard opens. It is empty until the first run.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '"This address cannot sign in" means you typed another address than your dashboard login: use the one you typed at the login step, usually your Supabase address.',
            '"Too many links were asked for" means waiting as long as it says.',
            'Supabase\'s own message "Email address not authorized" means the address is not the one of your Supabase account (see the login step).',
            `A link that opens \`localhost\` means the sign-in link was not connected: run \`${STEP_COMMAND.dashboard}\` again.`,
          ],
        },
      ],
    },
  ],
};
