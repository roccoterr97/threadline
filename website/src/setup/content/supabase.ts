import { SUPABASE_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { SUPABASE_TOKENS_PAGE } from './addresses';
import { STEP_COMMAND } from './commands';

/**
 * Mirrors part 2 of docs/setup-your-accounts.md, "Supabase (one token)":
 * the access token and the project (2a), the encryption key (2b) and the
 * database (2c). Set-up steps 1 to 3 of 11.
 */
export const SUPABASE: SetupPart = {
  id: 'supabase',
  title: 'Supabase (one token)',
  summary:
    'One access token lets the set-up create your database project, build the database and switch sign-ups off.',
  intro: [
    {
      kind: 'paragraph',
      text: 'Supabase is the database. You make **one access token** on Supabase\'s website, and the set-up does the rest: it creates the project (or reuses one of yours), waits until it is up, reads its address and keys, builds the database, and later switches off sign-ups. The token is kept in memory while the set-up runs and is **never saved**.',
    },
  ],
  steps: [
    {
      id: 'supabase-token-and-project',
      title: 'The token and your project',
      command: STEP_COMMAND.supabase,
      intro: [
        {
          kind: 'paragraph',
          text: 'This is `Step 1 of 11: Your Supabase project`. The set-up opens Supabase\'s **Access Tokens** page; you make a token there and paste it. Then it creates the project and waits for it to start, which takes one to three minutes.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'The set-up asks `Create the project (or pick an existing one) for you?`. Press Enter for yes.',
            `Supabase's **Access Tokens** page opens ([supabase.com/dashboard/account/tokens](${SUPABASE_TOKENS_PAGE})). Sign in if asked.`,
            'Click **Generate new token**. A form opens.',
            'Do not fill in that form. On the left, under **Resource access**, click the small link **Create legacy token**. Supabase\'s newer, limited tokens cannot read your project\'s secret key yet, and the set-up needs it. A legacy token can do everything the set-up does: create the project, read its keys, build the database and switch sign-ups off.',
            'Name it `Threadline set-up` and choose the **shortest expiry**: the token is only needed today.',
            'Click **Generate token**, copy it (it starts with `sbp_`), and paste it into the terminal. Nothing appears while you paste: that is on purpose.',
            'If you have several Supabase organisations, type the number of the one to use.',
            'If you already have projects, it lists them (`1. name (running)`, or `(still being set up)`) and asks `Use one of them instead of creating a new project?`. Press Enter for yes when a project named `threadline` is running or starting (it is most likely the one an earlier try made), otherwise Enter means no and creates a new one. Type the answer you want if the default is not it.',
            'Press Enter to accept the name `threadline`, then press Enter to accept the region it offers (the one nearest your time zone), or type another number.',
            'Wait while Supabase starts the project. This takes one to three minutes.',
          ],
        },
        {
          kind: 'warning',
          text: 'Do not press Ctrl + C while the project starts: it is already being created, and stopping leaves it half set up. The set-up warns you of this.',
        },
        {
          kind: 'note',
          text: 'The project\'s database password is made up for you and not kept: Threadline never needs it. If you ever do, reset it in Supabase under **Project Settings → Database**.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `The project is up.` (for a new project), then `Supabase accepted the address and both keys.`',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '`Supabase did not accept the access token`: copy the token again, all of it, and paste it once more. The set-up lets you try three times.',
            '`Supabase says this access token has too little access`: you made the newer, limited kind of token. Make a new one with the **Create legacy token** link (steps 3 to 6 above) and paste that one.',
            `\`your Supabase account has no organization yet\`: open [supabase.com](${SUPABASE_URL}), create an organisation (any name, free plan), then run \`${STEP_COMMAND.supabase}\`.`,
            `If Supabase refuses to create the project, your free plan may already have as many active projects as it allows. Run \`${STEP_COMMAND.supabase}\` again and answer yes to use an existing project, or pause a project you no longer use in Supabase first.`,
            `\`'name' is paused\`: open the project in Supabase and click **Restore project**, then run \`${STEP_COMMAND.supabase}\` again, or let it create a new project.`,
            `\`the project 'name' is still being set up after 5 minutes\`: the project is already created, so do not create another. Run \`${STEP_COMMAND.supabase}\` again in a while and pick it from the list (Enter picks it).`,
            '`a project may already have been created`: the request to create it was lost on the way. Run the step again and look at the list before creating anything.',
            `\`The project does not answer yet\` (a new project that is silent after about 30 seconds): wait a minute and run \`${STEP_COMMAND.supabase}\` again.`,
            `Running \`${STEP_COMMAND.supabase}\` again when \`.env\` already holds a complete project: it says \`Your .env already points to the Supabase project <ref>.\` and asks \`Keep it?\` (Enter keeps it) before it asks for any token.`,
          ],
        },
        {
          kind: 'note',
          text: '**If you prefer** to create the project yourself, answer **n** at step 1. The set-up then opens your Supabase projects and asks for the project address, the publishable key and the secret key (under **Project Settings → API Keys**, tab **Publishable and secret API keys**), checking each one as you paste it. The later steps then ask for an access token once, for the database.',
        },
      ],
    },
    {
      id: 'supabase-encryption-key',
      title: 'The encryption key',
      command: STEP_COMMAND.encryption,
      intro: [
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** everything. It makes a key that locks your Microsoft sign-in and your mailbox\'s app password inside the database, and saves it without showing it.',
        },
      ],
      youDo: [{ kind: 'paragraph', text: 'Nothing. Watch for the line below.' }],
      check: [
        {
          kind: 'paragraph',
          text: 'You see `A new key was made and saved.` (or, on a second run, `A usable key is already saved; it is kept.`)',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If it asks whether to replace an existing key, answer **no** unless you know the old one is wrong. A new key means signing in to Microsoft again.',
        },
      ],
    },
    {
      id: 'supabase-database',
      title: 'The database',
      command: STEP_COMMAND.database,
      intro: [
        {
          kind: 'paragraph',
          text: '**What the set-up does for you:** it looks at your new database, lists the structure files it needs, and applies them with the same token, one at a time, a second or two apart. This takes about half a minute. If Supabase refuses a file, the set-up shows Supabase\'s reason in one line and tries that file once more by itself.',
        },
        {
          kind: 'paragraph',
          text: `Run on its own later (\`${STEP_COMMAND.database}\`), the step first asks \`Apply them automatically?\`: press Enter, and paste a Supabase token made as in the step above. The token needs to read and write the database's **migrations** (its structure files); a legacy token covers that.`,
        },
      ],
      youDo: [{ kind: 'paragraph', text: 'Nothing during the first set-up. Watch the lines below.' }],
      check: [
        {
          kind: 'paragraph',
          text: 'The step starts with `To apply: 0001_schema, 0002_access_rules, …`, naming every file still missing (all of them on a new project). Then you see `Applied 0001_schema`, one line per file, and `The database structure is in place.`',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If a file still fails, or Supabase refuses the token when a file is sent, the set-up switches to the manual route by itself: it opens the **SQL Editor**, puts each file on your clipboard in turn, and waits.',
        },
        {
          kind: 'steps',
          items: [
            'For each file: click **+** for a new query, paste, click **Run**, and wait for `Success. No rows returned`.',
            'Only then press Enter in the terminal. Pressing Enter is not enough on its own: the set-up checks that the file really ran, and if it did not, it says `The database does not show … yet` and gives you the same file again.',
            `At the end it checks the database once more. If it still lists a file as missing, run \`${STEP_COMMAND.database}\` again.`,
          ],
        },
      ],
    },
  ],
};
