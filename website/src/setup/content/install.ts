import { INSTALL_LINE_MAC_LINUX, INSTALL_LINE_WINDOWS } from '../../constants/links';
import type { SetupPart } from '../types';
import { GITHUB_CLI_PAGE, WINGET_PAGE } from './addresses';
import {
  BACKEND_FOLDER_LINE,
  SETUP_BROWSER_COMMAND,
  SETUP_COMMAND,
  STEP_COMMAND,
} from './commands';

/**
 * Mirrors part 1 of docs/setup-your-accounts.md, "Install Threadline (one
 * line)": the line per computer, what it changes, the GitHub sign-in, and
 * where the later commands are typed.
 */
export const INSTALL: SetupPart = {
  id: 'install',
  title: 'Install Threadline (one line)',
  summary:
    'One line in a terminal installs the tools, signs you in to GitHub, makes your private copy and starts the guided set-up.',
  intro: [
    {
      kind: 'paragraph',
      text: 'One line gets Threadline onto your computer. It installs **uv** (the tool that runs Threadline) and the **GitHub tool** if they are missing, signs you in to GitHub, makes your own **private** copy of Threadline on GitHub (called `threadline`), downloads it to a `threadline` folder in your home folder, and starts the guided set-up.',
    },
    {
      kind: 'paragraph',
      text: '**What the install changes on your computer.** Besides those tools and the `threadline` folder, three things change, and the installer says so as it goes:',
    },
    {
      kind: 'bullets',
      platforms: ['mac', 'linux'],
      items: [
        '**uv\'s own installer adds uv to your PATH.** That is the list of places your terminal looks for programs. It adds a line to your shell\'s start-up file (such as `.zshrc` or `.profile`). This is why a new terminal finds `uv`.',
      ],
    },
    {
      kind: 'bullets',
      platforms: ['windows'],
      items: [
        '**uv\'s own installer adds uv to your PATH.** That is the list of places your terminal looks for programs. It adds uv\'s folder to your user PATH. This is why a new terminal finds `uv`.',
      ],
    },
    {
      kind: 'bullets',
      items: [
        '**`gh auth setup-git` lets git use your GitHub sign-in.** It adds a line to your git settings so that git, when it talks to github.com, asks the GitHub tool for your sign-in instead of asking for a password.',
        '**Git\'s name and e-mail are filled in if they are empty.** Git records both with every change. If you never set them, the installer sets them from your GitHub account: your name, and GitHub\'s private address (`number+yourname@users.noreply.github.com`), so your real address is not shown. It tells you what it set, and it never changes values you already set.',
      ],
    },
  ],
  steps: [
    {
      id: 'paste-the-line',
      title: 'Paste the line for your computer',
      intro: [
        {
          kind: 'paragraph',
          text: 'The line is safe to paste again at any time: it skips what is already done and carries on where things stopped.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          platforms: ['mac'],
          items: [
            'Open a terminal: press ⌘ + Space, type `Terminal`, press Enter.',
            'Paste the line below and press Enter.',
          ],
        },
        {
          kind: 'steps',
          platforms: ['windows'],
          items: [
            'Open the Start menu, type `PowerShell`, press Enter.',
            'Paste the line below and press Enter.',
            'If Windows asks whether to allow an installation, click **Yes**.',
          ],
        },
        {
          kind: 'steps',
          platforms: ['linux'],
          items: ['Open your terminal app.', 'Paste the line below and press Enter.'],
        },
        {
          kind: 'command',
          command: INSTALL_LINE_MAC_LINUX,
          platforms: ['mac', 'linux'],
          what: 'Installs Threadline on a Mac or Linux and starts the guided set-up.',
        },
        {
          kind: 'command',
          command: INSTALL_LINE_WINDOWS,
          platforms: ['windows'],
          what: 'Installs Threadline on Windows (in PowerShell) and starts the guided set-up.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The terminal reports what it installs, then says `Signing you in to GitHub` and shows a one-time code. (If this terminal is already signed in to GitHub, it skips that and goes on to make your copy.)',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: 'Every message that stops the installer says what to do, and pasting the line again is safe.',
        },
        {
          kind: 'bullets',
          platforms: ['mac'],
          items: [
            '`Git is not installed yet`: click **Install** in the window that offers the "command line developer tools", wait for it to finish, then paste the line again.',
          ],
        },
        {
          kind: 'bullets',
          platforms: ['windows'],
          items: [
            '`The installation of Git did not finish (code …)` (or the GitHub tool): Windows\' question "Do you want to allow this app to make changes?" was closed or answered No, or the connection dropped. Paste the line again and click **Yes**. If it keeps failing, install that tool by hand from the address the message gives, then paste the line again.',
            `\`Windows' installer (winget) is not on this computer\`: get **App Installer** from the Microsoft Store at [aka.ms/getwinget](${WINGET_PAGE}), then paste the line again.`,
          ],
        },
        {
          kind: 'bullets',
          items: [
            '`Could not download uv` or `Could not download the GitHub tool`: the internet connection dropped. Check it and paste the line again.',
            `\`The GitHub tool this computer uses is still version …\`: the installer could not replace an old GitHub tool. Install the newest from [cli.github.com](${GITHUB_CLI_PAGE}), open a new terminal, and paste the line again.`,
            '`… was installed but cannot be found yet`: close the terminal, open a new one, and paste the line again.',
          ],
        },
      ],
    },
    {
      id: 'github-sign-in',
      title: 'Sign in to GitHub with the one-time code',
      intro: [
        {
          kind: 'paragraph',
          text: 'The installer signs you in to GitHub in the browser, with the extra permission that saving the daily-run file later needs.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: [
            'When the terminal says `Signing you in to GitHub`, it shows a one-time code. Press Enter, and a GitHub page opens in your browser.',
            'Sign in and type the code.',
            'Before you click **Authorize**, check the account name at the top of the GitHub page. If it is not the account you want Threadline on, click **Use a different account** and sign in with the right one.',
            'Click **Authorize**. The page lists what it lets the GitHub tool do, including "workflow": that one is needed to save the daily-run file later.',
            'If the terminal asks whether to authenticate Git with your GitHub credentials, answer yes.',
          ],
        },
        {
          kind: 'warning',
          text: 'Check the account name at the top of the page before you click Authorize. Your private copy of Threadline is made on whichever GitHub account is signed in there.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'GitHub says the device is connected, and the terminal carries on: it makes your copy, downloads it and installs Threadline\'s parts.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '`… on GitHub is public`, `You are not the owner of …`, or `… is not a copy of Threadline`: your GitHub account already has a repository called `threadline` that is not your own private copy. Rename it on GitHub (Settings, then Repository name), or make it private if it is your copy, then paste the line again.',
            '`You are signed in to GitHub with the account that publishes Threadline`: that account holds Threadline itself, so it cannot have a copy of its own. Run `gh auth logout`, paste the line again, and sign in with another GitHub account.',
            '`Your copy on GitHub is not ready yet`: wait a minute and paste the line again.',
          ],
        },
      ],
    },
    {
      id: 'wait-for-the-set-up',
      title: 'Wait for the guided set-up to start',
      intro: [
        {
          kind: 'paragraph',
          text: 'The installer makes your copy, downloads it and installs Threadline\'s parts. This takes a minute or two. The first time, installing the parts can also download Python itself, which can take a few minutes more; that is normal.',
        },
      ],
      youDo: [
        {
          kind: 'steps',
          items: ['Wait. Do not close the terminal.'],
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'The terminal says `Starting the guided set-up`, then `Step 1 of 11: Your Supabase project`. Carry on with the Supabase part.',
        },
      ],
      ifNot: [
        {
          kind: 'bullets',
          items: [
            '`An earlier Threadline set-up is already on this computer`: you set up an older version in `~/tracker`. Press Enter to carry on with it, or type `n` to make a fresh copy in `~/threadline`.',
            '`… exists but is not a copy of Threadline`: you already have a different folder called `threadline` in your home folder. Rename it, then paste the line again.',
            'Anything else: the message says what to do. Pasting the line again skips what is already done and carries on.',
          ],
        },
      ],
    },
    {
      id: 'where-to-type-commands',
      title: 'Stopping, carrying on, and where to type the commands',
      intro: [
        {
          kind: 'paragraph',
          text: '**Stopping and carrying on.** You can stop the set-up at any time with Ctrl + C. Everything it has saved stays saved. To carry on, paste the install line again, or go to the `backend` folder as shown below and type `uv run tracker setup`.',
        },
        {
          kind: 'paragraph',
          text: '**If a step stops.** The set-up shows only plain sentences. The technical details go to a file called `setup.log` in the `backend` folder, and the set-up names that file when it stops. If you ask someone for help, show them that file. It never holds your keys.',
        },
        {
          kind: 'paragraph',
          text: '**What the set-up does next.** It runs 11 steps in order, numbered on screen (`Step 1 of 11`, `Step 2 of 11`, …). This guide follows the same order:',
        },
        {
          kind: 'table',
          rows: [
            ['Steps', 'Part of this guide'],
            ['1 to 3: Supabase, the encryption key, the database', 'Supabase (one token)'],
            ['4 to 6: your login, categories and time zone', 'Your login, categories and time zone'],
            ['7 and 8: your mailbox, and Outlook', 'Your mailbox and calendar'],
            ['9: the dashboard', 'The dashboard (Netlify)'],
            [
              '10 and 11: the daily time, the Claude key and the first run',
              'Run it every day on GitHub',
            ],
          ],
        },
        {
          kind: 'paragraph',
          text: `To run one step again later, name it, for example \`${STEP_COMMAND.database}\`. The optional extras (LinkedIn, the Refresh now button and the Claude cloud route) come later.`,
        },
      ],
      youDo: [
        {
          kind: 'paragraph',
          text: 'Every `uv run tracker …` command in this guide is typed in a terminal, inside the `backend` folder of your copy. In every new terminal window, type this first (it works from any folder):',
        },
        {
          kind: 'command',
          command: BACKEND_FOLDER_LINE,
          what: 'Goes to the folder where every Threadline command is typed.',
        },
        {
          kind: 'command',
          command: SETUP_COMMAND,
          what: 'Carries on with the guided set-up where it stopped.',
        },
        {
          kind: 'paragraph',
          text: '**Prefer a page to the terminal?** Add `--browser`. A page called *Threadline set-up* opens in your browser and asks the same questions, one at a time, with keys in hidden fields and a **Continue** button where this guide says "press Enter". The page is served to your computer only (its address starts with `http://127.0.0.1:`). The terminal still shows what is asked, never what you answer. A **Stop for now** link at the bottom ends the set-up cleanly; everything saved stays saved. `--browser` works with a single step and with the extras too, for example `uv run tracker setup database --browser`.',
        },
        {
          kind: 'command',
          command: SETUP_BROWSER_COMMAND,
          what: 'The same set-up, asked on a page in your browser instead of the terminal.',
        },
      ],
      check: [
        {
          kind: 'paragraph',
          text: 'Type `pwd` and press Enter. The folder it prints ends with `backend`.',
        },
      ],
      ifNot: [
        {
          kind: 'paragraph',
          text: '`Failed to spawn: tracker` or `No such file or directory` means the terminal is in another folder: type `cd ~/threadline/backend` and try again. If you set Threadline up before the one-line install existed, your copy may be in a folder called `tracker`: use that name instead of `threadline`.',
        },
      ],
    },
  ],
};
