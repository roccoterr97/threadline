import { CLAUDE_DOWNLOAD_URL, GITHUB_URL, GUIDE_URL } from '../../constants/links';
import type { ClaudeWay } from '../types';
import { CLAUDE_SETTINGS_PAGE } from './addresses';

/**
 * Mirrors docs/setup-with-claude.md, "The easy way: let Claude set it up for
 * you": one sentence pasted into the Claude app, which then does the
 * terminal work while the reader creates the accounts and clicks.
 */

/** The exact text to paste, word for word from docs/setup-with-claude.md. */
const PROMPT = `Please set up Threadline for me. I am not technical, so do all the terminal
work yourself and tell me in plain words what to click. Make my own private
copy of the template ${GITHUB_URL} in a folder
called threadline in my home folder, then follow its file
.claude/commands/setup.md from the first part to the last.`;

export const CLAUDE_WAY: ClaudeWay = {
  title: 'The easy way: let Claude set it up for you',
  summary:
    'One sentence pasted into the Claude app; Claude does the terminal work while you create the accounts and click where it says.',
  intro: [
    {
      kind: 'paragraph',
      text: 'Threadline runs on your own Claude subscription, and Claude can also do the set-up for you. You create two free accounts and click where it tells you; Claude does everything that happens in the terminal. Keys are typed by you into a page in your browser, never into the chat.',
    },
    {
      kind: 'paragraph',
      text: 'It takes about 20 minutes of your own time with GitHub and Supabase accounts ready, about 30 without. The first summary e-mail follows about ten minutes later, if you have a mailbox that can send it, for example Gmail with an app password.',
    },
    {
      kind: 'paragraph',
      platforms: ['mac', 'linux'],
      text: 'You need a paid Claude plan (Pro, Max or Team).',
    },
    {
      kind: 'paragraph',
      platforms: ['windows'],
      text: 'This way needs a Mac or a Linux computer and a paid Claude plan (Pro, Max or Team). On Windows, use the one-line install in the guided set-up instead: Claude can still answer your questions along the way.',
    },
    {
      kind: 'paragraph',
      text: `**1. Install the Claude app.** Download the Claude desktop app from [claude.ai/download](${CLAUDE_DOWNLOAD_URL}), open it and sign in with your Claude plan. Open the **Code** tab. The first time, it installs what it needs; when it asks for a folder, choose your home folder (the one with your name): Claude will make a \`threadline\` folder inside it.`,
    },
    {
      kind: 'paragraph',
      text: `Check: you see an empty conversation in the Code tab, ready to type in. If not: the Code tab appears only on paid plans; check at [claude.ai/settings](${CLAUDE_SETTINGS_PAGE}) that your plan is Pro, Max or Team.`,
    },
    {
      kind: 'paragraph',
      text: '**2. Paste this, and press Return.**',
    },
  ],
  prompt: PROMPT,
  afterwards: [
    {
      kind: 'paragraph',
      text: 'Claude will ask permission before it installs or runs anything; say yes when it explains what it is for. It will then take you through, one step at a time:',
    },
    {
      kind: 'steps',
      items: [
        '**Tools:** it installs the small helpers it needs (`uv`, `gh` and the Claude command-line tool) if they are missing.',
        '**Your private copy:** it makes your own copy of Threadline on GitHub (you may need to sign in to GitHub once, in the browser, with a code it gives you).',
        '**The accounts:** Supabase (the database; sign up with **Continue with GitHub**) and your mailbox\'s app password. These must be yours, so you create them, with Claude saying exactly what to click. The set-up then creates the database project for you.',
        '**The set-up page:** Claude starts the set-up and a page opens in your browser called *Threadline set-up*. It asks only what you must do, one question at a time; answer there. On Supabase you click **Authorize** and type the short code it shows into the set-up page. Then it asks your e-mail address and its app password. On Claude you click **Authorize**, and the key goes straight to GitHub. Everything else is chosen for you, and the end lists each choice with the command that changes it. Claude sees the questions, not your answers, and is told never to open that page itself (it could: the page\'s address appears in its window). Ask it anything that is unclear.',
        '**The first run:** the set-up starts it, Claude checks that it worked, and you look for the first summary e-mail. Claude then offers the Refresh now button, which also makes the daily run start on time.',
      ],
    },
    {
      kind: 'paragraph',
      text: '**Check:** at the end Claude shows `Everything Threadline needs is working.` and tells you your dashboard\'s personal link. **If not:** tell Claude what you see on the screen. It can run any step again; nothing already finished is lost.',
    },
    {
      kind: 'warning',
      text: 'Keys never go in the chat. The set-up page in your browser is where you paste them. It is served to your computer only. If you paste a key in the chat by mistake, make a new one on the page where you made it and use that.',
    },
    {
      kind: 'bullets',
      items: [
        '**Nothing is sent to anybody.** Everything lives in accounts you own; the only e-mail Threadline ever sends is the morning summary, to you.',
        `**Doing it by hand instead.** Every step Claude runs is a plain command. The guided set-up on this site, and [the written guide](${GUIDE_URL}), are the full way to do it yourself; add \`--browser\` to any \`uv run tracker setup\` command to get the same page instead of terminal prompts.`,
        'Later, open the `threadline` folder with Claude again and type `/setup` followed by a part (`wizard`, `first run`…) to redo it.',
      ],
    },
  ],
};
