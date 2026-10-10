import type { SetupPart } from '../types';
import { ASK_EVERYTHING_COMMAND, STEP_COMMAND } from './commands';

/**
 * Mirrors part 3 of docs/setup-your-accounts.md, "Your login, categories and
 * time zone": the dashboard login (3a), the categories (3b) and the time
 * zone (3c). Set-up steps 4 to 6 of 11.
 */
export const LOGIN_CATEGORIES_TIME_ZONE: SetupPart = {
  id: 'login-categories-time-zone',
  title: 'Your login, categories and time zone',
  summary:
    'The one e-mail address that can open the dashboard, the categories people are sorted into, and what "today" means.',
  steps: [
    {
      id: 'dashboard-login',
      title: 'Your dashboard login',
      command: STEP_COMMAND.login,
      intro: [
        {
          kind: 'paragraph',
          text: 'The dashboard only lets in the one login recorded as its owner. Nobody else can create a login, so nobody else can read your data.',
        },
        {
          kind: 'paragraph',
          text: '**Which e-mail address to use.** You sign in to the dashboard with a link Supabase e-mails to you. Supabase\'s built-in e-mail sends only **two messages an hour**, and **only to the address your Supabase account was registered with (or to members of your Supabase organisation)**. So use the same address you signed up to Supabase with. (Another address needs your own e-mail sending service, called "custom SMTP" in Supabase. This guide does not cover it.)',
        },
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it reads the address of your Supabase account (with your Supabase sign-in), creates your login for it, records it as the only owner, and switches off sign-ups in Supabase. It says which address it is: `Your dashboard login is you@example.com, the address of your Supabase account`. Note it: that is where the sign-in link goes.',
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: `Nothing, usually. If the set-up could not read that address (for example when you carry on a set-up started earlier), it asks \`E-mail address for the dashboard\` once: type the address you signed up to Supabase with, and press Enter. If you signed in to Supabase with GitHub, it is the main e-mail address of your GitHub account; Supabase shows it under **Account → Preferences**. Run on its own (\`${STEP_COMMAND.login}\`), the step always asks, offering your Supabase account's address.`,
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `… can now sign in to the dashboard, and nobody else can read it.` and then `Sign-ups are now switched off: nobody else can create a login.` (or `Sign-ups are switched off` if they already were). A later run that finds the login done says `Your dashboard login: …` under `Already done`.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If Supabase would not change the setting (also after a Supabase server error or a timeout), the set-up opens the page **Authentication → Sign In / Providers**. Switch off **Allow new users to sign up**, click **Save**, and press Enter in the terminal. If the switch keeps coming back on, reload the page, switch it off again and click **Save** before pressing Enter.',
        },
      ],
    },
    {
      id: 'categories',
      title: 'Your categories',
      command: STEP_COMMAND.categories,
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: `Threadline puts each person you talk to in a category, such as "Startup" or "Investor". The set-up keeps the job-search categories without asking (\`Kept the usual job-search categories.\`). Change them any time on the dashboard's **Settings** page, or run \`${STEP_COMMAND.categories}\`, which asks the questions below.`,
        },
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it saves your categories to your database and tells the AI helper about them.',
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: `Nothing during the first set-up. When you run \`${STEP_COMMAND.categories}\` (or the whole set-up with \`${ASK_EVERYTHING_COMMAND}\`):`,
        },
        {
          kind: 'steps',
          items: [
            `Answer **y** to "Choose your categories now?" (or **n** to skip; it won't ask again, and \`${STEP_COMMAND.categories}\` brings it back).`,
            'Type the number of the list closest to what you track, for example `3` for a job search or `5` for sales. Press Enter to accept the number it suggests.',
            'It lists the suggested categories and asks "Use all of them?". Press Enter to keep them all. If you type `n`, it asks about each one: press Enter to keep it, or type `n` to drop it.',
            'To add one of your own, answer **y**, then type its name ("Supplier"), a name for a group (press Enter to accept "Suppliers"), who belongs there in one sentence ("Companies that sell to us") and a colour (press Enter to accept the one offered). The sentence matters: the AI helper reads it to decide who goes where. Answer **n** when you have no more to add.',
            'Look at the list it shows, then press Enter to save it.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `Kept the usual job-search categories.` during the first set-up, or `Saved … categories, \'Not known\' included.` after choosing. Once your dashboard is ready, its **Settings** page shows the same categories.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `"That did not work" means a name was empty, too long, already in your list, or the colour was not one of those offered: type it again. If you answered **n** by mistake, run \`${STEP_COMMAND.categories}\` again.`,
        },
      ],
    },
    {
      id: 'time-zone',
      title: 'Your time zone',
      command: STEP_COMMAND.timezone,
      intro: [
        {
          kind: 'paragraph',
          text: `**What the set-up does for you:** it reads the time zone your computer uses and takes it without asking: \`Your time zone: Europe/Paris.\` Only if it cannot tell (a Windows zone name it does not know, for example) does it say "I could not tell your time zone" and wait for you to type it. Run on its own (\`${STEP_COMMAND.timezone}\`), the step offers the zone, such as \`Your time zone [Europe/Paris]:\`, and asks for your name too.`,
        },
        {
          kind: 'paragraph',
          text: 'Your time zone decides what "today" is for due dates and the summary, and the daily run\'s time (the GitHub part) is read in it. It is saved as `OWNER_TIME_ZONE` and later sent to GitHub with your other settings. When the zone differs from the one in the daily run\'s workflow file (`.github/workflows/threadline-run.yml`), it writes the new zone there too, keeping the time, and sends it to your copy on GitHub (run on its own, the step shows the line it changed and asks first).',
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: `Nothing during the first set-up, unless it asks you to type your zone. When you run \`${STEP_COMMAND.timezone}\` (or the whole set-up with \`${ASK_EVERYTHING_COMMAND}\`):`,
        },
        {
          kind: 'steps',
          items: [
            'Press Enter (or type `y`) to keep the zone offered, or type yours in the same form (`America/New_York`, `Asia/Tokyo`, `UTC`). When no zone is offered you must type one; an empty answer is asked again. Capital letters do not matter: `europe/rome` is accepted and saved as `Europe/Rome`.',
            'It then asks for your name as people write it (such as `Sam Rivera`). This is optional: it helps only when your e-mail address does not spell your name (`jd123@…`). Leave it empty and press Enter to skip it.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `Your time zone: …` with your zone (or `Saved OWNER_TIME_ZONE=…` when the step is run on its own).',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `"that is not a time-zone name" means it was typed in another form: use the region and the city with a slash, such as \`Europe/Rome\`. To change it later, run \`${STEP_COMMAND.timezone}\`.`,
        },
      ],
    },
  ],
};
