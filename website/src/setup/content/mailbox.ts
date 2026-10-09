import { OPERATIONS_URL } from '../../constants/links';
import type { SetupPart, SetupStep } from '../types';
import {
  APPLE_ACCOUNT_PAGE,
  GOOGLE_APP_PASSWORDS_PAGE,
  GOOGLE_SECURITY_PAGE,
  YAHOO_SECURITY_PAGE,
} from './addresses';
import { DOCTOR_COMMAND, STEP_COMMAND } from './commands';

/**
 * Mirrors part 4 of docs/setup-your-accounts.md, "Your mailbox and calendar":
 * choosing the mailbox (4a), the app password for Gmail, iCloud, Yahoo,
 * Fastmail or any other mailbox (4b), and Outlook (4c). Set-up steps 7 and 8
 * of 11. Only the step for your own mailbox applies.
 */

const GENERAL_CHECK =
  'The terminal shows `Connected. Your inbox has … messages from the last 30 days.`, then `Your own replies are read from the folder \'…\'.` and `Saved the app password, encrypted, in your database - it is not in .env.`';

const CHOOSE_MAILBOX: SetupStep = {
  id: 'choose-mailbox',
  title: 'Choose your mailbox',
  command: STEP_COMMAND.mailbox,
  intro: [
    {
      kind: 'paragraph',
      text: 'The set-up asks: "Which mailbox should Threadline read? gmail, outlook, icloud, yahoo, fastmail or other".',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'Type one word and press Enter.',
        '**outlook** (also for Hotmail and Live): go on to the Outlook step at the end of this part.',
        '**anything else**: do the step for your provider below (Gmail, iCloud, Yahoo, Fastmail or any other mailbox), and skip the others.',
      ],
    },
    {
      kind: 'warning',
      text: `With Outlook alone, the run on GitHub cannot e-mail you the morning summary, because Microsoft allows no app password for sending. Connect a Gmail or other mailbox as well (run \`${STEP_COMMAND.mailbox}\` again later), or use the Claude cloud route in the extras.`,
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: 'The set-up either asks for your address (Gmail and the others) or says the Microsoft step signs you in (Outlook).',
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: 'If it says "please answer gmail, outlook, …", type one of those words exactly.',
    },
  ],
};

const APP_PASSWORD_INTRO = [
  {
    kind: 'paragraph',
    text: 'Gmail, iCloud, Yahoo and Fastmail do not let other programs use your normal password. Instead you make an **app password**: a separate password just for Threadline, which you can remove at any time. Your normal password is never given to Threadline.',
  },
  {
    kind: 'paragraph',
    text: '**What the set-up does for you:** it asks for your address, explains app passwords, opens your provider\'s page, and waits for you to paste the new password (nothing is shown while you paste). Then it **checks it live**: it signs in, opens your inbox read-only, counts the messages of the last 30 days and looks for your Sent folder. Only then does it store the password, encrypted, in your database, **never in `.env`**, and offer to add the address to your own addresses.',
  },
] as const;

const GENERAL_IF_NOT = {
  kind: 'paragraph',
  text: '"refused the app password" means the password was copied wrongly, belongs to another address, or the account does not allow app passwords. The set-up lets you paste again twice. "No Sent folder was found" still works, but your own replies will not be read: tell the project which folder your mail program saves sent mail in.',
} as const;

const GMAIL: SetupStep = {
  id: 'gmail',
  onlyFor: ['gmail'],
  title: 'Gmail: the app password',
  intro: [
    { kind: 'paragraph', text: 'Only if your mailbox is Gmail.' },
    ...APP_PASSWORD_INTRO,
    {
      kind: 'paragraph',
      text: `Good to know: IMAP is always on for personal Gmail accounts, so there is no setting to switch on. **Changing your Google password removes every app password**: see "Renew a mailbox app password" in [operations.md](${OPERATIONS_URL}).`,
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        `**Turn on 2-Step Verification.** Open [myaccount.google.com/security](${GOOGLE_SECURITY_PAGE}), find **2-Step Verification** and follow Google's steps (you need your phone). The page may look slightly different. Check: the Security page shows 2-Step Verification as **on**. If not, finish Google's steps; app passwords appear only once it is on.`,
        `**Make the app password.** Type \`gmail\` and your Gmail address in the terminal. The set-up opens [myaccount.google.com/apppasswords](${GOOGLE_APP_PASSWORDS_PAGE}). Sign in if asked, type a name such as \`Threadline\`, and create it. The page may look slightly different. Check: Google shows a 16-character password. Copy it now: Google shows it only once.`,
        '**Paste it in the terminal** and press Enter. Spaces do not matter.',
      ],
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: `${GENERAL_CHECK} The folder is \`[Gmail]/Sent Mail\` (or its name in your language).`,
    },
  ],
  ifNot: [
    {
      kind: 'bullets',
      items: [
        'If Google says the app-password setting is not available, one of these is true: 2-Step Verification is off; you sign in only with security keys; Advanced Protection is on; or it is a work or school account whose administrator switched app passwords (or IMAP) off. Only the administrator can change the last one: use Outlook instead, or ask them.',
        'If the set-up refused the password, make a new app password and paste that one.',
      ],
    },
    GENERAL_IF_NOT,
  ],
};

const ICLOUD: SetupStep = {
  id: 'icloud',
  onlyFor: ['icloud'],
  title: 'iCloud Mail: the app-specific password',
  intro: [
    { kind: 'paragraph', text: 'Only if your mailbox is iCloud Mail.' },
    ...APP_PASSWORD_INTRO,
    {
      kind: 'paragraph',
      text: 'Good to know: changing or resetting your Apple Account password removes every app-specific password.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        `**Two-factor authentication** must be on for your Apple Account (it usually is). Check: at [account.apple.com](${APPLE_ACCOUNT_PAGE}), **Sign-In and Security** lists **App-Specific Passwords**. If not, turn on two-factor authentication on your iPhone or Mac first.`,
        `**Make the password.** Type \`icloud\` and your iCloud address. The set-up opens [account.apple.com](${APPLE_ACCOUNT_PAGE}). Sign in, open **Sign-In and Security** → **App-Specific Passwords** → **Generate an app-specific password**, name it \`Threadline\`, and follow the steps. The page may look slightly different. Check: Apple shows the new password. If not, check you are signed in with the Apple Account that owns the mailbox.`,
        '**Paste it in the terminal.**',
      ],
    },
  ],
  check: [{ kind: 'paragraph', text: GENERAL_CHECK }],
  ifNot: [
    {
      kind: 'paragraph',
      text: `Apple's help says the sign-in name is usually the part of your address **before the @**. Run \`${STEP_COMMAND.mailbox}\` again, answer \`other\`, server \`imap.mail.me.com\`, port \`993\`, and type only the part before the @ as the sign-in name. When it asks for the sending server, type \`smtp.mail.me.com\` and port \`587\`.`,
    },
    GENERAL_IF_NOT,
  ],
};

const YAHOO: SetupStep = {
  id: 'yahoo',
  onlyFor: ['yahoo'],
  title: 'Yahoo Mail: the app password',
  intro: [
    { kind: 'paragraph', text: 'Only if your mailbox is Yahoo Mail.' },
    ...APP_PASSWORD_INTRO,
    {
      kind: 'paragraph',
      text: 'Good to know: Yahoo keeps app passwords when you change your password; remove old ones yourself on the same page.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        `**Make the app password.** Type \`yahoo\` and your Yahoo address. The set-up opens [login.yahoo.com/account/security](${YAHOO_SECURITY_PAGE}). Under **External connections**, click **Create app password**, type \`Threadline\`, then **Generate password**. The page may look slightly different. Check: Yahoo shows a new password.`,
        '**Paste it in the terminal**, then click **Done** on Yahoo\'s page.',
      ],
    },
  ],
  check: [{ kind: 'paragraph', text: GENERAL_CHECK }],
  ifNot: [
    {
      kind: 'bullets',
      items: [
        'Yahoo sometimes refuses to make the password from a browser it does not know yet. Use a browser you usually sign in to Yahoo with, not a private window, and try again later.',
        'If the set-up refused the password, make a new app password and paste that one.',
      ],
    },
    GENERAL_IF_NOT,
  ],
};

const FASTMAIL: SetupStep = {
  id: 'fastmail',
  onlyFor: ['fastmail'],
  title: 'Fastmail: the app password',
  intro: [
    { kind: 'paragraph', text: 'Only if your mailbox is Fastmail. IMAP needs a paid Fastmail plan above Basic.' },
    ...APP_PASSWORD_INTRO,
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        '**Make the app password.** Type `fastmail` and your Fastmail address. The set-up opens Fastmail\'s help page about app passwords. In Fastmail, open **Settings** → **Privacy & Security** → **Connected apps & API tokens** → **Manage app passwords and access** → **New app password**. Choose a name, set the access to **Mail (IMAP/POP/SMTP)**, then **Generate password**. The page may look slightly different. Check: Fastmail shows a 16-character password.',
        '**Paste it in the terminal.** Wait for the check to pass before clicking **Done** on Fastmail\'s page.',
      ],
    },
  ],
  check: [{ kind: 'paragraph', text: GENERAL_CHECK }],
  ifNot: [
    {
      kind: 'bullets',
      items: [
        'If there is no such setting, your plan does not include IMAP.',
        'If the set-up refused the password, make a new app password with Mail access and paste that one.',
      ],
    },
    GENERAL_IF_NOT,
  ],
};

const OTHER_MAILBOX: SetupStep = {
  id: 'other-mailbox',
  onlyFor: ['other'],
  title: 'Any other mailbox',
  intro: [
    {
      kind: 'paragraph',
      text: 'Only if your mailbox is none of the above. Any mailbox that offers IMAP works.',
    },
    ...APP_PASSWORD_INTRO,
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'In your provider\'s help pages, find its **IMAP server** name (such as `imap.example.com`) and port (almost always `993`), and how to make an **app password**. If your provider offers no app passwords, it may accept your normal password; Threadline stores it encrypted the same way, but an app password is safer because you can remove it on its own.',
        'Type `other`, then the server, the port (press Enter for 993), the name you sign in with (usually your address), and paste the password.',
        'Once your mailbox is saved, the set-up asks for the **sending server** (SMTP), which it needs to e-mail you the morning summary from this mailbox (it skips this when you chose another way to send the summary). Your provider\'s help pages list it next to the IMAP server. It suggests a name (for `imap.example.com` it offers `smtp.example.com`): press Enter to accept it, or type the right one. Then type the port, **465** or **587** (press Enter for 465). The set-up signs in to that server once with the same app password, to catch a wrong server now rather than every morning. It sends nothing.',
      ],
    },
  ],
  check: [
    {
      kind: 'paragraph',
      text: `${GENERAL_CHECK} Then you see \`Signed in to the sending server. Nothing was sent.\``,
    },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: `"did not answer" means the server name or port is wrong, or the provider does not offer it over TLS on that port. The set-up asks \`Try another server or port?\`: press Enter to try again, or type \`n\` to carry on without it for now. After three tries it carries on by itself. Either way your mailbox stays connected and is read every morning; only the morning summary cannot be e-mailed yet. Check the name and port in your provider's help pages, then run \`${STEP_COMMAND.mailbox}\` again: it asks for the app password once more (make a new one if you no longer have it) and then for the sending server. Then run \`${STEP_COMMAND.github}\`, so the run on GitHub is told the sending server too. A sending server saved for a different mailbox is removed at this point, so the summary is never sent through the wrong one. Later, \`${DOCTOR_COMMAND}\` shows a **Summary e-mail** line for the sending server.`,
    },
    GENERAL_IF_NOT,
  ],
};

const OUTLOOK: SetupStep = {
  id: 'outlook',
  title: 'Outlook mailbox and calendar',
  command: STEP_COMMAND.microsoft,
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: `If you chose another mailbox, this step asks first whether to connect Outlook as well. Answer **no** to skip it: the set-up remembers that and won't ask again (it says \`Skipped earlier\`). You can add it later with \`${STEP_COMMAND.microsoft}\`.`,
    },
    {
      kind: 'paragraph',
      text: '**The calendar is read from Outlook only, for now.** With Gmail alone, Threadline reads your e-mail, including interview invitations that arrive by mail, but not your Google Calendar.',
    },
    {
      kind: 'paragraph',
      text: '**What the set-up does for you:** it asks Microsoft for a short one-time code, opens Microsoft\'s page, waits while you sign in, stores the resulting key encrypted in your database, and reads your calendar once to show who signed in. From then on the key renews itself every day.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'Type the code shown in the terminal on the Microsoft page that opens.',
        'Sign in with your Outlook.com or Hotmail account.',
        'Microsoft lists the permissions: **read your mail**, **read your calendars**, and **keep access**. All are read-only. Click **Accept** (or **Yes**).',
        'Back in the terminal, answer **yes** when it offers to save the signed-in address as one of your own.',
      ],
    },
  ],
  check: [
    { kind: 'paragraph', text: 'You see `Signed in as you@example.com.` with your own address.' },
  ],
  ifNot: [
    {
      kind: 'paragraph',
      text: `If Microsoft says the code expired, run \`${STEP_COMMAND.microsoft}\` again: you have fifteen minutes to type it. If Microsoft refuses the application itself, see the next step, "Your own Microsoft application".`,
    },
  ],
};

const OWN_MICROSOFT_APPLICATION: SetupStep = {
  id: 'own-microsoft-application',
  title: 'Your own Microsoft application',
  optional: true,
  intro: [
    {
      kind: 'paragraph',
      text: 'By default the sign-in goes through the public application of an open-source project (ms-365-mcp-server). That is enough for almost everybody. Only read on if you would rather use your own.',
    },
    {
      kind: 'paragraph',
      text: 'Since June 2024 Microsoft only lets you register an application inside a directory, and **a personal Microsoft account alone cannot do that**. You need a free Azure account, which comes with a directory.',
    },
  ],
  youDo: [
    {
      kind: 'steps',
      items: [
        'In the Microsoft Entra admin centre: **App registrations → New registration**; account type **Personal Microsoft accounts only**; then **Authentication → Allow public client flows: Yes → Save**; then add the delegated Microsoft Graph permissions `Mail.Read`, `Calendars.Read` and `offline_access`. (The exact clicks were not checked and the pages may look slightly different.)',
        `Put the application's ID in \`.env\` as \`MICROSOFT_CLIENT_ID=…\` and run \`${STEP_COMMAND.microsoft}\` again.`,
      ],
    },
  ],
  check: [{ kind: 'paragraph', text: '`Signed in as …` appears with your own address.' }],
  ifNot: [
    {
      kind: 'paragraph',
      text: `Remove the \`MICROSOFT_CLIENT_ID\` line from \`.env\` to go back to the default, and run \`${STEP_COMMAND.microsoft}\` again.`,
    },
  ],
};

export const MAILBOX: SetupPart = {
  id: 'mailbox',
  title: 'Your mailbox and calendar',
  summary:
    'The mailbox Threadline reads, read-only, with an app password; and Outlook, which also gives the calendar.',
  intro: [
    {
      kind: 'paragraph',
      text: 'Threadline needs **at least one mailbox**: Gmail, Outlook.com/Hotmail, iCloud, Yahoo, Fastmail, or any other mailbox that offers IMAP. It only ever reads: nothing is sent, moved, deleted, or even marked as read.',
    },
    {
      kind: 'paragraph',
      text: 'Answer the question below and only the step for your mailbox stays on the page. Outlook comes last and is optional when you read another mailbox.',
    },
  ],
  choice: {
    id: 'mailbox',
    question: 'Which mailbox will Threadline read?',
    options: [
      { id: 'gmail', label: 'Gmail' },
      { id: 'outlook', label: 'Outlook.com or Hotmail' },
      { id: 'icloud', label: 'iCloud' },
      { id: 'yahoo', label: 'Yahoo' },
      { id: 'fastmail', label: 'Fastmail' },
      { id: 'other', label: 'Another mailbox' },
    ],
  },
  steps: [CHOOSE_MAILBOX, GMAIL, ICLOUD, YAHOO, FASTMAIL, OTHER_MAILBOX, OUTLOOK, OWN_MICROSOFT_APPLICATION],
};
