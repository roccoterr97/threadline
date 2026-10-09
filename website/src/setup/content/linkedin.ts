import type { SetupPart, SetupStep } from '../types';
import {
  CLAUDE_CODE_WEB,
  LINKEDIN_APPS_PAGE,
  LINKEDIN_NEW_APP_PAGE,
  LINKEDIN_REDIRECT_ADDRESS,
  LINKEDIN_TOKEN_GENERATOR_PAGE,
} from './addresses';
import { DOCTOR_COMMAND, STEP_COMMAND } from './commands';

/**
 * Mirrors part 8a of docs/setup-your-accounts.md, "LinkedIn": the three
 * stages that connect a LinkedIn developer application to Threadline, making
 * the key by hand as the fallback, sending the key to GitHub, and the
 * one-command renewal (also "Renew the LinkedIn key" in docs/operations.md).
 */

const CREATE_APPLICATION: SetupStep = {
  id: 'linkedin-create-application',
  title: 'Stage 1 of 3: create the developer application',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: `The set-up opens LinkedIn's "Create an app" form, [linkedin.com/developers/apps/new](${LINKEDIN_NEW_APP_PAGE}). Sign in to LinkedIn if it asks.`,
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        '**App name:** anything, for example `Threadline`.',
        '**LinkedIn Page:** type `Member Data Portability` and choose the page LinkedIn suggests for this product, **Member Data Portability (Member) Default Company**. Do **not** create a new page.',
        'If the form asks for an **App logo**, upload any small square picture (a screenshot works).',
        'Tick the terms and click **Create app**.',
        'Go back to the terminal and press Enter.',
      ],
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: 'Your new application\'s page opens with tabs such as **Settings**, **Auth** and **Products**.',
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: `If LinkedIn asks you to verify the page, make sure you picked the default company named above. If you already created the application on an earlier try, do not make a second one: open [linkedin.com/developers/apps](${LINKEDIN_APPS_PAGE}) and click it in the list instead.`,
    },
  ],
};

const ADD_PRODUCT: SetupStep = {
  id: 'linkedin-add-product',
  title: 'Stage 2 of 3: add the Member Data Portability product',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'Stay on your application\'s page, the one stage 1 ended on.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'Open its **Products** tab.',
        'Find **Member Data Portability API (Member)** and click **Request access**.',
        'Read and accept the terms.',
        'In the terminal, answer **yes** to "Did LinkedIn let you request access?" (or press Enter).',
      ],
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: 'The product is listed under the products your application has (the page may look slightly different).',
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: 'If LinkedIn says the product is not available to you, your profile is most likely not located in the EEA or Switzerland. Answer **no**. The set-up says `Skipped: …`, saves nothing, and Threadline carries on without LinkedIn.',
    },
  ],
};

const CONNECT_APPLICATION: SetupStep = {
  id: 'linkedin-connect-application',
  title: 'Stage 3 of 3: connect the application to Threadline',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'Stay on your application\'s page. You do this stage once; later keys need only the **Allow** click in step 6.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'Open its **Auth** tab.',
        'Under **OAuth 2.0 settings**, click the pencil next to **Authorized redirect URLs for your app**, then **+ Add redirect URL**.',
        'Paste the address below, exactly as it is, and click **Update**. The set-up has already put it on your clipboard.',
        'Go back to the terminal and press Enter.',
        'At the top of the same **Auth** tab, under **Application credentials**: copy the **Client ID**, paste it in the terminal and press Enter. Then click the eye icon next to **Primary Client Secret**, copy it, paste it in the terminal and press Enter. Nothing appears as you paste the secret; that is on purpose.',
        'LinkedIn\'s page opens and asks to let your application read your data. Sign in if asked and click **Allow**. The tab then says `Threadline has LinkedIn\'s answer. You can close this tab and go back to the set-up.`',
        'The first time only, paste your profile address (`https://www.linkedin.com/in/…`) in the terminal.',
      ],
    },
    {
      kind: 'value',
      value: LINKEDIN_REDIRECT_ADDRESS,
      what: 'The redirect address to add on the Auth tab, exactly as it is.',
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: 'You see `LinkedIn made a new key. It works until …` with a date, then `LinkedIn accepted the key.`, then `Saved LINKEDIN_CLIENT_ID in .env.`, `Saved the Client Secret, encrypted, in your Supabase database.` and the same `Saved …` line for `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_TOKEN_EXPIRES_ON` and `OWNER_LINKEDIN_PROFILE_URL`.',
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: 'Each problem has its own line. After it, answer **y** to `Try again?` and the set-up opens LinkedIn\'s page again (up to three tries).',
    },
    {
      kind: 'bullets',
      items: [
        'LinkedIn\'s own page shows **"The redirect_uri does not match the registered value"**: the address in step 3 is not exactly the one above. Fix it on the **Auth** tab. After two minutes the terminal asks `No answer from LinkedIn yet. Keep waiting?`: answer **n**, then **y** to `Try again?`. When it asks for the Client ID and Client Secret again, press Enter to keep what you typed.',
        'LinkedIn\'s own page shows **"invalid client_id"**: the Client ID was not copied whole. Do as in the line above and type the Client ID again.',
        '`LinkedIn did not accept the Client ID or the Client Secret`: copy both again from the **Auth** tab when the set-up asks.',
        '`LinkedIn has not given your application the … product yet`: check the **Products** tab (stage 2). Wait a few minutes after requesting it.',
        '`LinkedIn says the sign-in was cancelled`: you clicked **Cancel** or did not sign in. Try again and click **Allow**.',
        '`Another program on this computer is using port 8746`: another set-up is probably still open in a different terminal window. Close it and try again.',
      ],
    },
    {
      kind: 'paragraph',
      text: 'If it still does not work, answer **n** to `Try again?`: the set-up offers to make the key by hand instead (next step).',
    },
  ],
};

const BY_HAND: SetupStep = {
  id: 'linkedin-key-by-hand',
  title: 'Making the key by hand',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'This is the older way, and it always stays available. The set-up offers it when the one-click way did not work (`Make the key by hand on LinkedIn\'s token page instead?`), and on a renewal when you answer **n** to `Set that up now?`.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        `The set-up opens LinkedIn's token page, [linkedin.com/developers/tools/oauth/token-generator](${LINKEDIN_TOKEN_GENERATOR_PAGE}) (in LinkedIn's own menu: **Docs and tools → OAuth Token Tools → Create token**).`,
        'Pick your application.',
        'Tick the permission (scope) whose name starts with **`r_dma_portability`**. LinkedIn\'s own pages name it slightly differently in different places.',
        'Click **Request access token**, sign in if asked, and click **Allow**.',
        'Copy the token LinkedIn shows. It is shown only once. Paste it in the terminal and press Enter. Nothing appears as you paste; that is on purpose.',
        'If you typed the Client ID and Client Secret in stage 3, the set-up asks LinkedIn when the key expires and shows `LinkedIn says this key works until …`. Otherwise it asks you for that day: open **Docs and tools → OAuth Token Tools → Token Inspector** on the same LinkedIn page, pick your application, paste the token, click **Inspect** and type the expiry date it shows. `2027-09-24`, `24 Sep 2027`, `24 September 2027` and `Sep 24, 2027` all work. A date with only numbers and slashes, such as `03/04/2027`, is refused, because it could mean two different days.',
      ],
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: 'You see `LinkedIn accepted the key.`, then `Saved LINKEDIN_ACCESS_TOKEN in .env.` and the same line for `LINKEDIN_TOKEN_EXPIRES_ON`.',
    },
  ],
  ifNot: [
    {
      kind: 'bullets',
      items: [
        'If **Request access token** is greyed out, the product from stage 2 has not been approved yet: wait a few minutes and reload.',
        '"wrong or has expired": make a new token (steps 2 to 5) and paste that one; the set-up asks up to three times.',
        '"lacks the data portability permission": you ticked a different permission in step 3.',
        '"that date has already passed": type the day the key **expires**, not the day it was made.',
      ],
    },
  ],
};

const SEND_TO_GITHUB: SetupStep = {
  id: 'linkedin-send-to-github',
  title: 'Send it to GitHub',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'The daily run on GitHub only learns about LinkedIn once the new values are there. Right after saving them, the set-up says so and asks `Send them to … on GitHub now?`. It saves just the LinkedIn key, its expiry date and (the first time) your profile address, never shows a value, and does not ask for the Claude key again. The Client ID and Client Secret stay on your computer and in your database: the daily run does not need them.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: ['Press Enter for yes at `Send them to … on GitHub now?`.'],
    },
    {
      kind: 'paragraph',
      text: `If you answered **n**, or the GitHub tool is not signed in, it prints \`To send them later, run: ${STEP_COMMAND.github}\`. Run that command, press Enter when it asks for the Claude key (GitHub keeps the one it has), press Enter to save, and answer **n** when it offers to start a daily run, unless you want one now.`,
    },
  ],
  check: [
    { kind: 'paragraph', text: 'The list includes `secret LINKEDIN_ACCESS_TOKEN saved`.' },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: `Run \`${STEP_COMMAND.github}\` and read the line where it stopped.`,
    },
  ],
};

const RENEW: SetupStep = {
  id: 'linkedin-renew',
  title: 'When the key expires: one command and one click',
  command: STEP_COMMAND.linkedin,
  minutes: 1,
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'The key that lets Threadline read your LinkedIn messages works until a date LinkedIn sets; the set-up saved that date when you made the key. Seven days before it, every morning summary carries a "LinkedIn key" line with the exact date. Renewing it takes about a minute.',
    },
    {
      kind: 'paragraph',
      text: 'A key is already saved, so the set-up skips stages 1 and 2. If your application is connected (stage 3), LinkedIn\'s page opens at once. You copy nothing and type no date.',
    },
  ],
  youDo: [
    {
      kind: 'command',
      command: STEP_COMMAND.linkedin,
      what: 'Makes a new LinkedIn key; typed in the backend folder.',
    },
    {
      kind: 'steps',
      items: [
        'LinkedIn\'s page opens in your browser. Sign in if asked and click **Allow**. If you are still signed in, LinkedIn may not even ask: the page says `Threadline has LinkedIn\'s answer` straight away. The set-up checks the new key with LinkedIn and saves it with the day it expires.',
        `Press Enter (yes) at \`Send them to … on GitHub now?\` to put the new key where the daily run reads it; otherwise it keeps using the old one. If you answered no, run \`${STEP_COMMAND.github}\` (press Enter when it asks for the Claude key, to keep the one GitHub has, and answer \`n\` when it offers to start a daily run).`,
      ],
    },
    {
      kind: 'paragraph',
      text: 'If you connected LinkedIn by hand, before this one-click way existed, the set-up offers it once: answer **yes** to `Set that up now?` and do steps 1 to 6 of stage 3 (add one address on your LinkedIn application\'s **Auth** tab and copy two values). Answer **n** to keep making the key by hand.',
    },
    {
      kind: 'paragraph',
      text: `On the Claude cloud route, update \`LINKEDIN_ACCESS_TOKEN\` and \`LINKEDIN_TOKEN_EXPIRES_ON\` in the cloud environment at [claude.ai/code](${CLAUDE_CODE_WEB}) instead; \`${STEP_COMMAND.cloud}\` puts each value on your clipboard in turn.`,
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: `You see \`LinkedIn made a new key. It works until …\` and \`secret LINKEDIN_ACCESS_TOKEN saved\`. \`${DOCTOR_COMMAND}\` says \`ok  LinkedIn key\` and shows the new date.`,
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: 'The same lines as in stage 3\'s **if not** apply.',
    },
  ],
};

export const LINKEDIN: SetupPart = {
  id: 'linkedin',
  title: 'LinkedIn',
  summary:
    'Read your LinkedIn messages too: a small developer application, connected once; after that a new key is one command and one click.',
  intro: [
    {
      kind: 'paragraph',
      text: 'LinkedIn offers no ready-made sign-in button for this, so the first time you make a small "developer application" on LinkedIn\'s pages and connect it to Threadline. After that, a new key is one command and one click. Before you decide, here is what to expect:',
    },
    {
      kind: 'bullets',
      items: [
        '**It is optional.** Everything else works without LinkedIn.',
        '**It depends on where your LinkedIn profile is located.** LinkedIn offers this only to members whose profile is located in the European Economic Area or Switzerland. It is the location on your profile that counts, not your citizenship. If you live elsewhere, skip LinkedIn.',
        '**LinkedIn messages appear a day or two late.** LinkedIn\'s copy of your messages runs one to two days behind (measured on 24 September 2026), so a message you receive on LinkedIn today shows up in Threadline tomorrow or the day after. Nothing is lost; it only arrives later.',
        '**The first time takes about ten minutes.** When the key expires, you run one command and click **Allow** once.',
      ],
    },
    {
      kind: 'paragraph',
      text: '**What the set-up does for you:** it takes you through three stages in order and opens the right LinkedIn page for each one. In the last stage it puts the address you need on your clipboard, opens LinkedIn\'s **Allow** page, catches LinkedIn\'s answer on your own computer, and reads from LinkedIn the day the key expires, so you never copy the key or type a date. It makes one small call to LinkedIn with the new key and saves it only if LinkedIn accepts it. The application\'s Client Secret is kept encrypted in your Supabase database, never in a plain file.',
    },
    {
      kind: 'paragraph',
      text: '**What you do:** answer **yes** to "Connect LinkedIn now?" (or press Enter to skip LinkedIn), then follow the stages below as the pages open.',
    },
    {
      kind: 'command',
      command: STEP_COMMAND.linkedin,
      what: 'Runs the LinkedIn step on its own, any time after the core set-up.',
    },
  ],
  steps: [CREATE_APPLICATION, ADD_PRODUCT, CONNECT_APPLICATION, BY_HAND, SEND_TO_GITHUB, RENEW],
};
