import type { SetupPart } from '../types';
import { GITHUB_CLI_PAGE } from './addresses';
import {
  ASK_EVERYTHING_COMMAND,
  CLAUDE_TOKEN_COMMAND,
  DOCTOR_COMMAND,
  SETUP_COMMAND,
  STEP_COMMAND,
} from './commands';

/**
 * Mirrors part 6 of docs/setup-your-accounts.md, "Run it every day on
 * GitHub: the Claude key and the first run": the daily time (6a), the Claude
 * key and the settings on GitHub (6b), the first run (6c) and seeing it
 * (6d). Set-up steps 10 and 11 of 11.
 */
export const GITHUB: SetupPart = {
  id: 'github',
  title: 'Run it every day on GitHub',
  summary:
    'The daily time, the key that lets GitHub use your Claude plan, and the first run, which starts by itself.',
  intro: [
    {
      kind: 'paragraph',
      text: 'Every morning GitHub starts Threadline on your private copy, runs the daily job with **your own Claude subscription**, and e-mails you the summary from your own mailbox, with your computer off. At the time of writing, GitHub\'s free plan includes 2,000 minutes a month for private repositories; one run takes about five to ten minutes, so a month of mornings uses roughly 150 to 300.',
    },
    {
      kind: 'paragraph',
      text: '**Which mailbox sends the summary.** Threadline sends it from the Gmail, iCloud, Yahoo, Fastmail or other mailbox you connected in the mailbox part, with the same app password (no new password to make). If you connected **only Outlook**, it cannot: Microsoft requires its own sign-in method (OAuth2) for Outlook.com, Hotmail and Live mail programs, and turned off plain passwords and app passwords for them in September 2024. You have two choices: connect a Gmail or other mailbox as well (Threadline can read both), or use the Claude cloud route in the extras, which sends through Claude\'s Gmail connector.',
    },
    {
      kind: 'paragraph',
      text: `The GitHub step checks this before it does anything. If no mailbox with an app password is connected, it says so plainly (run on its own, it also offers to run the mailbox step right then). The first run still starts, to fill the dashboard, but nothing promises you an e-mail: the dashboard is updated every morning, but no summary e-mail arrives until you connect a mailbox (\`${STEP_COMMAND.mailbox}\`, then \`${STEP_COMMAND.github}\`) or switch to the cloud route.`,
    },
  ],
  steps: [
    {
      id: 'daily-time',
      title: 'The daily time',
      command: STEP_COMMAND.schedule,
      intro: [
        {
          kind: 'paragraph',
          text: `**What the set-up does for you:** it keeps the time already set, 07:00 unless you chose another before, and says how to change it (\`To change the time: ${STEP_COMMAND.schedule}\`). The time is read in the time zone you gave earlier and written, with the zone, into the workflow file \`.github/workflows/threadline-run.yml\`, then sent to your copy on GitHub. GitHub follows your summer and winter time by itself.`,
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: `Nothing during the first set-up. When you run \`${STEP_COMMAND.schedule}\` (or the whole set-up with \`${ASK_EVERYTHING_COMMAND}\`):`,
        },
        {
          kind: 'steps',
          items: [
            'Type the time on the 24-hour clock, such as `07:07`, or press Enter to keep the one offered (07:00 unless you chose another before). GitHub\'s own timer is busiest on the hour and often starts a run late, sometimes by hours; the Refresh now extra makes your Supabase project start it on time instead.',
            'When it asks `Send the new time to your copy on GitHub now?`, press Enter (yes). GitHub only uses the new time once the change is uploaded.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `Committed and pushed. GitHub will use the new time from now on.`, or `The daily run already starts at …` when nothing needed changing.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            `If you answered **n**, run the \`git\` lines the set-up printed (they work from any folder of the project), or run \`${STEP_COMMAND.schedule}\` again and answer **y**: the set-up notices that GitHub does not have your time yet and offers the upload again, even though the file itself needs no change.`,
            `If the set-up stops with \`Stopped: git does not know who you are, so it cannot save the change\`, git has no name to put on the change yet. Run \`git config --global user.name "Your Name"\` and \`git config --global user.email "you@example.com"\` once, with your own name and address, then run \`${SETUP_COMMAND}\` again. Any other reason git gives is shown in the same line, after \`git said:\`.`,
            `To use a different time zone later, run \`${STEP_COMMAND.timezone}\`: it moves the workflow's zone too, keeping the time.`,
          ],
        },
      ],
    },
    {
      id: 'claude-key',
      title: 'The Claude key and your settings on GitHub',
      command: STEP_COMMAND.github,
      intro: [
        {
          kind: 'paragraph',
          text: 'The run on GitHub cannot read the `.env` file on your computer, so your settings go into your copy\'s **secrets** (hidden in every log) and **variables** (the harmless ones, such as your time zone). GitHub also needs a key that lets it use your Claude subscription. The set-up makes that key for you with Claude Code, which the install line added.',
        },
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it saves every secret and variable on your copy and names each one as it goes, never its value. The **secrets** include the Claude key, your Supabase keys, the encryption key, your own addresses (`OWNER_EMAIL_ADDRESSES`), and, when you have set them, `IMAP_USERNAME`, `DASHBOARD_BASE_URL` and `OWNER_DISPLAY_NAME`. The **variables** are the harmless settings, such as `OWNER_TIME_ZONE`, `MAIL_SOURCES` and `IMAP_PROVIDER`.',
        },
        {
          kind: 'paragraph',
          text: 'If you emptied a setting on your computer (for example you removed `OWNER_DISPLAY_NAME` from `.env`) and GitHub still holds it, the set-up lists each one by name and asks once whether to delete them on GitHub, so the daily run stops using the old values. Press Enter to delete them, or type `n` to keep them.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          platforms: ['mac', 'linux'],
          items: [
            'A Claude page opens by itself. Sign in if asked, with the account of your Claude plan, and click **Authorize**. The key goes straight to GitHub: you never see or copy it. It lasts one year.',
            'The window shows only the set-up\'s own lines. If no page opened, it shows the address to open. If the Claude page shows a code instead, paste it in the set-up\'s window and press Enter.',
            'The set-up then saves your settings on GitHub without asking (`Saving … secrets and … variables in … with the GitHub CLI.`).',
          ],
        },
        {
          kind: 'paragraph',
          platforms: ['mac', 'linux'],
          text: `Run on its own (\`${STEP_COMMAND.github}\`), the step asks before each of these: press Enter for yes. When GitHub already has a Claude key, it asks \`GitHub already has a Claude key. Make a new one now?\`. Enter keeps the key GitHub has.`,
        },
        {
          kind: 'paragraph',
          platforms: ['mac', 'linux'],
          text: '**If the set-up says `The key could not be made here`**, it asks you to paste the key instead:',
        },
        {
          kind: 'paragraph',
          platforms: ['windows'],
          text: 'On Windows you make the key yourself and paste it; the set-up then saves your settings on GitHub. To make and paste the key:',
        },
        {
          kind: 'steps',
          items: [
            'Open a **second** terminal window and type the line below.',
            'Sign in in the browser that opens, then go back to that second window: it prints a long key that starts with `sk-ant-oat`. The key is split over two lines. Copy it from the first letter to the last, including the second line.',
            'Paste it into the set-up in the first window (nothing shows while you paste) and press Enter. If the key looks cut short, the set-up asks you to paste its second line, or the whole key again. Pressing Enter on an empty line keeps the key GitHub already has, if any.',
          ],
        },
        {
          kind: 'command',
          command: CLAUDE_TOKEN_COMMAND,
          what: 'Makes the key by hand, only if the set-up asks you to paste it; type it in a second terminal window.',
        },
        {
          kind: 'warning',
          text: 'The key is never saved on your computer, not even in `.env`. Anyone with this key can use your Claude subscription, so never paste it anywhere else.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The list names every secret and variable it set, ending with `Done. GitHub has everything it needs to run Threadline on your copy.`',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            `If the Claude page did not open, or you closed it, run \`${STEP_COMMAND.github}\` again.`,
            `\`That key is cut short\`, \`That is an API key\` or \`That is not the key\` means a pasted key was not the whole key from \`${CLAUDE_TOKEN_COMMAND}\`. Go back to the second window and copy it again, from \`sk-ant-oat\` to the last letter of the second line, and paste it when the set-up asks again.`,
            `If GitHub has no key, the set-up does not start the first run, because the run would do nothing. Run \`${STEP_COMMAND.github}\` again.`,
            'If the set-up stopped with `there is no private copy on GitHub yet`, this folder is not linked to your own private copy. Paste the install line again: it makes the copy and downloads it.',
            `If it stopped with \`your GitHub CLI is too old\`, the \`gh\` on your computer is from before 2.68 and lacks commands Threadline uses. Install the newest from [cli.github.com](${GITHUB_CLI_PAGE}) (or run the install line again), then run \`${STEP_COMMAND.github}\`. The set-up says this at the first use of \`gh\`, not at the end.`,
          ],
        },
      ],
    },
    {
      id: 'first-run',
      title: 'The first run starts by itself',
      intro: [
        {
          kind: 'paragraph',
          text: `Right after saving, and once it has seen that GitHub holds your Claude key, the set-up makes sure GitHub Actions and the workflow are switched on in your copy, then starts the run, without asking. (Run on its own, \`${STEP_COMMAND.github}\` asks \`Start the first daily run on GitHub now?\` first: press Enter for yes. When no summary e-mail can be sent from GitHub, the question says so and Enter means no.)`,
        },
        {
          kind: 'paragraph',
          text: 'The set-up then watches the run for up to two minutes, to catch a problem early (`Watching it for up to 2 minutes, to catch a problem early...`).',
        },
      ],
      youDo: [{ kind: 'paragraph', text: 'Nothing. Watch for the lines below.' }],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `The first run has started.`, then `It is running; the summary e-mail comes in about 10 minutes.` and the address of the run\'s page. (If the run already finished, it says `The first run has finished.` instead.)',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            `\`The first run stopped with a problem.\`, followed by the reason: do what that line says. Most often it is \`Claude did not accept the key saved on GitHub\`. Run \`${STEP_COMMAND.github}\` again: it makes a new key the same way (if it asks you to paste one, paste both lines), and answer yes to start a new first run.`,
            'If GitHub refused to start the run, the set-up says so in one line and names the page where you start the run yourself: open that page (**Actions → Threadline run** in your copy on GitHub); if it shows **Enable workflow**, click it. Then click **Run workflow**, keep **mode: daily**, and click the green **Run workflow** button.',
            'The same two clicks apply if you set Threadline up without the installer and the set-up could not use the GitHub tool: it then lists the setting names to add on **Settings → Secrets and variables → Actions**, puts each value on your clipboard in turn, and ends with those two clicks.',
          ],
        },
      ],
    },
    {
      id: 'see-the-run',
      title: 'See the run, and the e-mail',
      intro: [
        {
          kind: 'paragraph',
          text: 'On the run\'s page, a new run appears with a yellow dot and, after about five to ten minutes, has a green tick. Open the finished run and click **Threadline**, then **Run the recipe with Claude**: the log ends with Claude\'s short report of the run, in plain English. It never contains the text of your messages.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Open the run\'s page (the set-up printed its address) and wait for the green tick.',
            'Look in your inbox for the summary e-mail, and open the dashboard\'s **Daily runs** page.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'Within about ten minutes of the start, the summary e-mail is in your inbox, sent from your own mailbox, and the dashboard\'s **Daily runs** page shows the run as **Worked** or **Partly worked**.',
        },
        {
          kind: 'note',
          text: 'From now on the run starts by itself every day at the time you chose, as GitHub\'s timer allows; with Refresh now switched on (an extra), exactly on time.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            `**Green tick after a few seconds, nothing sent:** a required secret is missing. Open the run; a note at the top names the missing secrets. Run \`${STEP_COMMAND.github}\` again.`,
            `*Red cross:* open the run. When Claude stopped with an error, a line titled **Why Claude stopped** at the top of the run's page says why, such as a refused key, the plan's usage limit, or Claude being busy, and what to do. For a refused key, run \`${STEP_COMMAND.github}\` again: it makes a new key. Without that line, click **Threadline** and open the step with the red cross.`,
            `*Green tick but no e-mail:* a green tick only means the job ran, not that every part worked. Read Claude's report at the end of the log, then run \`${DOCTOR_COMMAND}\` on your computer: its **Summary e-mail** line checks that your mailbox accepts the app password for sending, without sending anything.`,
            '*A run stopped half-way (cancelled, or GitHub stopped it):* nothing to clean up. The dashboard\'s **Daily runs** page shows it as **Running** for a while; when the next run starts (at least three hours later), it is closed as **Did not work**, with the step where it stopped marked "The run stopped here and never finished", and the next morning summary mentions it once.',
          ],
        },
      ],
    },
  ],
};
