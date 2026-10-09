import { OPERATIONS_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { CLAUDE_CODE_WEB, CLAUDE_GITHUB_APP_PAGE, CLAUDE_ROUTINES_PAGE } from './addresses';
import { DOCTOR_COMMAND, STEP_COMMAND } from './commands';

/**
 * Mirrors part 8c of docs/setup-your-accounts.md, "The Claude cloud route",
 * briefly: the alternative to the daily run on GitHub, for people who read
 * only Outlook.
 */
export const CLOUD_ROUTE: SetupPart = {
  id: 'cloud-route',
  title: 'The Claude cloud route',
  summary:
    'Instead of GitHub: a Claude cloud routine runs the daily job and sends the summary through Claude\'s Gmail connector.',
  intro: [
    {
      kind: 'paragraph',
      text: 'Use this instead of the daily run on GitHub only if GitHub does not suit you, most often because you read **only Outlook**, whose mail programs cannot send with an app password. A Claude cloud routine sends the summary through Claude\'s Gmail connector, so you also need a Google account with Gmail.',
    },
    {
      kind: 'warning',
      text: `Do not run both routes: you would get two e-mails. Once your Claude routine has run once and the e-mail arrived, switch the GitHub daily run off: \`gh workflow disable threadline-run.yml\`. At the end of this part the set-up offers to do it for you, with the answer set to no; answer yes only if the routine already runs. To do it by hand, or to switch it on again, see "Pause and resume" in [operations.md](${OPERATIONS_URL}).`,
    },
    {
      kind: 'paragraph',
      text: `Set \`SUMMARY_DELIVERY=gmail_connector\` in \`.env\` if you also read a Gmail or other IMAP mailbox: a Claude cloud session can most likely reach only web addresses, not the mail ports that sending by SMTP needs. This part is done on [claude.ai/code](${CLAUDE_CODE_WEB}) and cannot be automated from your computer.`,
    },
    {
      kind: 'command',
      command: STEP_COMMAND.cloud,
      what: 'Lists what the cloud needs and puts each value on your clipboard in turn.',
    },
  ],
  steps: [
    {
      id: 'cloud-open-your-copy',
      title: 'Let Claude open your copy of Threadline',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'Claude on the web can only run the daily job in a repository it has been given access to.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            `Go to [github.com/apps/claude](${CLAUDE_GITHUB_APP_PAGE}), install the **Claude** GitHub app, and give it access to your Threadline copy only.`,
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: `At [claude.ai/code](${CLAUDE_CODE_WEB}) your Threadline copy appears in the list of repositories.`,
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'Open the Claude app\'s settings on GitHub and add the repository.',
        },
      ],
    },
    {
      id: 'cloud-environment',
      title: 'Create the cloud environment',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'Answer **yes** when the set-up asks whether to set up the Claude cloud routine instead.',
        },
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it lists the **names** of the variables the cloud needs (never their values), lists the web addresses the cloud must be allowed to reach, and offers to put each value on your clipboard in turn so you never have to open `.env`.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            `At [claude.ai/code](${CLAUDE_CODE_WEB}), click the cloud icon with the environment name above the message box, then **Add cloud environment**.`,
            '**Name:** for example `Threadline`.',
            '**Network access:** **Custom**. In **Allowed domains**, add one per line the domains the set-up printed: your project\'s `….supabase.co` address; `graph.microsoft.com` (only if you connected Outlook); your mailbox\'s IMAP server, such as `imap.gmail.com` (only if you connected Gmail or another IMAP mailbox); `api.linkedin.com` (only if you connected LinkedIn). Tick **Also include default list of common package managers**. It already covers Microsoft\'s sign-in address, `login.microsoftonline.com`.',
            '**Environment variables:** one per line as `NAME=value`. Use the names the set-up printed. Usually they are `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `TOKEN_ENCRYPTION_KEY`, `OWNER_EMAIL_ADDRESSES`, the mailbox settings (`MAIL_SOURCES`, `IMAP_PROVIDER`, `IMAP_USERNAME`), `OWNER_LINKEDIN_PROFILE_URL`, `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_TOKEN_EXPIRES_ON` and `DASHBOARD_BASE_URL`. For each one, type `NAME=`, go back to the terminal and press Enter to get the value onto the clipboard, then paste it.',
            'Save the environment.',
          ],
        },
        {
          kind: 'warning',
          text: 'Anyone who can use this environment can read these values, so keep it to yourself.',
        },
        {
          kind: 'note',
          text: `Reading Gmail and other IMAP mailboxes is not web traffic: it uses port 993. Whether a Claude cloud environment lets that through was not checked when the guide was written. The doctor in the check below tells you: if its \`IMAP mailbox\` line says the mailbox "did not answer" although the server is in the list, use the Mac route (see [operations.md](${OPERATIONS_URL})).`,
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: `Start a session in this environment, on your Threadline copy, and ask it to run \`cd backend && ${DOCTOR_COMMAND}\`. Every line says \`ok\` (optional parts may say \`skipped\`).`,
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'A `PROBLEM` line says what to fix. "could not be reached" in the cloud almost always means a missing allowed domain. "missing or wrong" names a missing variable. Change the environment, then start a **new** session: changes only reach sessions started afterwards.',
        },
      ],
    },
    {
      id: 'cloud-connect-gmail',
      title: 'Connect Gmail',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'The routine sends the summary through Claude\'s Gmail connector.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'In Claude, open **Customize → Connectors**, click **+**, choose **Gmail** and click **Connect**.',
          ],
        },
      ],
      check: [{ kind: 'paragraph', text: 'Gmail is listed as connected.' }],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'Disconnect it and connect it again, making sure you allow sending.',
        },
      ],
    },
    {
      id: 'cloud-routine',
      title: 'Create the routine',
      optional: true,
      intro: [
        {
          kind: 'paragraph',
          text: 'A routine is a Claude session that starts by itself on a schedule.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            `Go to [claude.ai/code/routines](${CLAUDE_ROUTINES_PAGE}) and click **New routine**.`,
            '**Name:** for example `Threadline daily run`.',
            '**Repository:** your Threadline copy. **Environment:** the one from the step before.',
            '**Prompt:** `Run the daily-run command from this repository.`',
            '**Connectors:** keep **Gmail**, and **remove every other connector**. In a routine, connectors act without asking you first. Gmail can send e-mail, so leave nothing attached that the job does not need.',
            '**Schedule:** daily, at a time a few minutes past the hour, for example **07:07** (times are in your own time zone).',
            'Save, then click **Run now** once.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'Within about ten minutes, the summary e-mail arrives in your inbox, and the dashboard\'s **Daily runs** page shows the run as **Worked** or **Partly worked**.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `A green routine status only means the session ran, not that the job worked. Open the session and read its last message. Then run \`${DOCTOR_COMMAND}\` on your computer: it names what is wrong, one line each.`,
        },
      ],
    },
  ],
};
