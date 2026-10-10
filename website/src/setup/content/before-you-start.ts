import { GITHUB_SIGNUP_URL, SUPABASE_URL } from '../../constants/links';
import type { SetupPart } from '../types';
import { GITHUB_CLI_PAGE, GIT_FOR_WINDOWS_PAGE, WINGET_PAGE } from './addresses';

/**
 * Mirrors "Before you start" of docs/setup-your-accounts.md: what you need,
 * the accounts to create first, the time it takes, and the words the guide
 * uses before it explains them.
 */
export const BEFORE_YOU_START: SetupPart = {
  id: 'before-you-start',
  title: 'Before you start',
  summary:
    'The accounts to create first, what the set-up needs on your computer, and how long it takes.',
  intro: [
    {
      kind: 'paragraph',
      text: 'This guide takes you from nothing to the first summary e-mail, one small step at a time. You do not need to know how to program. You paste one line into a terminal, and a guided set-up does most of the work. Where only you can do something, such as creating an account or clicking **Allow**, this guide says exactly what to click.',
    },
    {
      kind: 'paragraph',
      text: 'After every step there is a **check** (what you should see if it worked) and an **if not** (what to do if you see something else). Do not skip a check: each step builds on the one before it.',
    },
    {
      kind: 'note',
      text: 'Websites change. Button names were right when this guide was written. Where a page may look slightly different, the guide says so. Look for a button with a similar name.',
    },
    {
      kind: 'paragraph',
      text: '**Time.** About 20 minutes of your own time with GitHub and Supabase ready, about 30 without. Part of it is waiting: a new Supabase project takes one to three minutes to start, and the first download of Python can take a few more. Making a Gmail app password takes longer if 2-Step Verification is not on yet. You can stop at any point: the set-up carries on where you left off.',
    },
    {
      kind: 'paragraph',
      text: 'The first summary e-mail follows about ten minutes after the set-up ends, but only if you have a mailbox that can send it, for example Gmail with an app password. With Outlook alone the dashboard fills and no e-mail comes; the Claude cloud route in the extras is for that.',
    },
    {
      kind: 'paragraph',
      text: '**What it costs.** No other paid service is needed. GitHub, Supabase, Google, Microsoft and LinkedIn are all used on their free plans; the only exception would be a paid mailbox you choose yourself, such as Fastmail. Free-plan limits change, so check the providers\' pricing pages if in doubt.',
    },
    {
      kind: 'paragraph',
      platforms: ['mac', 'linux'],
      text: '**Your keys.** The settings the set-up saves are kept in a file called `.env` in your Threadline folder. Only you can read it. Some keys are never saved at all: the set-up uses them and forgets them, and this guide says which.',
    },
    {
      kind: 'paragraph',
      platforms: ['windows'],
      text: '**Your keys.** The settings the set-up saves are kept in a file called `.env` in your Threadline folder. The folder is inside your user folder, which other ordinary accounts on the computer cannot open by default (an administrator can); the file itself has no extra lock. Some keys are never saved at all: the set-up uses them and forgets them, and this guide says which.',
    },
    {
      kind: 'warning',
      text: 'Never paste a key into a chat, an e-mail or a document.',
    },
    {
      kind: 'paragraph',
      text: '**Words used here.** A few words come up before they are explained:',
    },
    {
      kind: 'table',
      rows: [
        ['Word', 'What it means'],
        [
          'IMAP and SMTP',
          'IMAP is the standard way a program reads a mailbox; SMTP is the standard way it sends mail. Your provider\'s help pages give a server name for each.',
        ],
        [
          'App password',
          'A separate password made for one program only, which you can remove without changing your real password.',
        ],
        [
          'Secrets and variables',
          'The settings the run on GitHub reads. A secret is hidden in every log; a variable is a harmless setting shown in the open.',
        ],
        ['cron', 'The line in the workflow file that says at what time the run starts each day.'],
        [
          'Edge Function',
          'A small helper that runs inside your Supabase project; the Refresh now button uses one.',
        ],
        [
          'Management API',
          'The official way the set-up talks to Supabase on your behalf, after you let it in once with **Authorize**.',
        ],
        ['CRM', 'Customer-relationship software, which Threadline is not.'],
        [
          'EEA',
          'The European Economic Area: the EU plus Iceland, Liechtenstein and Norway.',
        ],
      ],
    },
  ],
  steps: [
    {
      id: 'what-you-need',
      title: 'What you need',
      intro: [
        {
          kind: 'table',
          rows: [
            ['What', 'Why'],
            [
              'A computer with macOS, Linux or Windows (10 or 11)',
              'To run the set-up once. After that it can stay off.',
            ],
            [
              'A paid Claude plan: Pro, Max or Team',
              'Runs the daily job on GitHub with your own subscription, with your computer off. The daily run uses part of your plan\'s usage limits, like any other use of Claude.',
            ],
            [
              'A GitHub account',
              'Keeps your private copy of Threadline and runs it every day (GitHub Actions). Free: 2,000 minutes a month for private copies at the time of writing; a month of runs uses about 150 to 300.',
            ],
            ['A Supabase account', 'The database that keeps your people and conversations. Free plan.'],
            [
              'At least one mailbox',
              'Gmail, Outlook.com/Hotmail, iCloud, Yahoo, Fastmail or any mailbox that offers IMAP: the mail Threadline reads, read-only. Gmail and the others also send you the summary. Free (Fastmail: a paid plan above Basic).',
            ],
            [
              'Optional: a Microsoft personal account',
              'Outlook.com, Hotmail or Live: the calendar, which is read from Outlook only for now. Free.',
            ],
            [
              'Optional: a LinkedIn account',
              'Reads your LinkedIn messages too (only for members located in the EEA or Switzerland). Free.',
            ],
          ],
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'Go down the table and note what you already have.',
            'The next steps on this page create the accounts you are missing. Do them before you paste the install line: the set-up asks for Supabase in its very first step.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You have a paid Claude plan (Pro, Max or Team), and you know which mailbox Threadline will read.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'Without a paid Claude plan the daily run has nothing to run on: the key it uses comes from your subscription. With only an Outlook mailbox, Threadline can read your mail and fill the dashboard, but cannot e-mail you the summary; the extras explain the two ways round that.',
        },
      ],
    },
    {
      id: 'your-computer',
      title: 'What the installer needs on your computer',
      intro: [
        {
          kind: 'paragraph',
          text: 'The one-line install adds the tools Threadline uses, Claude Code included. What it needs from you depends on your computer.',
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          platforms: ['windows'],
          text: 'Nothing extra on most computers. The installer adds Git and the GitHub tool with **winget**, Windows\' own installer, part of the "App Installer" that current Windows 10 and Windows 11 come with. Some Windows 10 editions (LTSC, Server, or an older build) do not have it.',
        },
        {
          kind: 'paragraph',
          platforms: ['mac'],
          text: 'Git must be installed. If it is not, the Mac offers to install it (the "command line developer tools") the first time. Homebrew is not needed: with Homebrew the installer uses it for the GitHub tool; without it, the installer downloads GitHub\'s own build for your Mac into the `.local/bin` folder in your home folder and checks it against GitHub\'s published checksums.',
        },
        {
          kind: 'paragraph',
          platforms: ['linux'],
          text: 'Git and curl must be installed. The installer adds the GitHub tool from GitHub\'s own apt or dnf package source (the one `cli.github.com` describes), because the version your distribution offers is often too old, and may ask for your computer\'s password. Without apt, dnf or the right to install packages, it downloads GitHub\'s own build into `~/.local/bin` instead.',
        },
        {
          kind: 'note',
          text: 'The GitHub tool must be version 2.68 or newer. The installer checks the one you have and updates it if it is older.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'Nothing to do now: the installer says what it needs as it goes.',
        },
        {
          kind: 'paragraph',
          platforms: ['mac'],
          text: 'A window may offer to install the command line developer tools.',
        },
        {
          kind: 'paragraph',
          platforms: ['windows'],
          text: 'A question may ask whether to allow an installation.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: `If the installer says winget is missing on Windows, get **App Installer** from the Microsoft Store at [aka.ms/getwinget](${WINGET_PAGE}), or install Git from [git-scm.com](${GIT_FOR_WINDOWS_PAGE}) and the GitHub tool from [cli.github.com](${GITHUB_CLI_PAGE}), then paste the install line again.`,
        },
      ],
    },
    {
      id: 'github-account',
      title: 'A GitHub account',
      intro: [
        {
          kind: 'paragraph',
          text: 'GitHub keeps your private copy of Threadline and runs it every day. The install line signs you in to GitHub, so the account must exist first.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            `If you have no GitHub account yet, sign up at [github.com/signup](${GITHUB_SIGNUP_URL}).`,
            'Sign in to it in your usual browser: that is the browser the set-up opens pages in.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'Your account name shows at the top of the GitHub page, and it is the account you want Threadline on.',
        },
      ],
      ifNot: [
        {
          kind: 'warning',
          text: 'Pages open in your default browser. If that browser is signed in to a different GitHub, Supabase or Claude account than the one you want to use, check the account name at the top of the page before you click anything. If it is the wrong one, copy the page\'s address into a window signed in to the right account.',
        },
      ],
    },
    {
      id: 'supabase-account',
      title: 'A Supabase account',
      intro: [
        {
          kind: 'paragraph',
          text: 'Supabase is the database that keeps your people and conversations. The set-up asks for it in its very first step, so create the account now.',
        },
        {
          kind: 'paragraph',
          text: '**The sign-in e-mail limit.** You will sign in to the dashboard with a link that Supabase e-mails to you. Supabase\'s built-in e-mail only reaches the address your Supabase account was registered with (or members of your Supabase organisation), unless you set up your own sending service ("custom SMTP"). With **Continue with GitHub**, that is your GitHub account\'s main e-mail address.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            `Sign up at [supabase.com](${SUPABASE_URL}) with **Continue with GitHub**. One click.`,
            'If Supabase asks you to create an organisation, do it: any name, free plan.',
          ],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'You are signed in to Supabase and it shows an organisation (it can be empty, with no project yet).',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'If the set-up later says `your Supabase account has no organization yet`, open Supabase, create an organisation (any name, free plan), and run the Supabase step again.',
        },
      ],
    },
  ],
};
