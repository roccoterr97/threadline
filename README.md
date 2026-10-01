# Threadline

**Every conversation, one clear line.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Threadline is a private, self-hosted tool for the conversations you are keeping
alive: who you are talking to, where each conversation stands, who owes whom a
reply, and what to do next.

Once a day it reads your new LinkedIn messages, your Microsoft personal
mailbox (Outlook.com / Hotmail) and its calendar, throws away the noise, and
groups what is left into one timeline per person. An AI step, run by Claude on
your own subscription, then judges each person: the status, who is waiting on
whom, the next action and when it is due. You see the result on a private
dashboard, and a short summary e-mail reaches you every morning.

Threadline started as a job-search tool and is being generalised. You pick a
preset — job search, sales outreach, fundraising, freelance clients or general
networking — or define your own categories. See
[`docs/customising.md`](./docs/customising.md).

## Try the demo

Live demo: <https://threadline-seven-delta.vercel.app>

See the dashboard with made-up data before setting anything up. You need
[Node.js](https://nodejs.org) 22 or newer; no accounts and no settings.

```bash
cd frontend
npm install
npm run demo
```

Then open <http://localhost:5173>. You are signed in as an invented owner who
does sales outreach. You can correct people, answer the review questions and
change the categories on the Settings page; nothing is saved, and reloading the
page starts again from the same made-up data. A demo build is made with
`npm run build:demo`; a normal build never contains the demo. To put the demo
online as its own website, follow [`docs/demo-site.md`](./docs/demo-site.md).

## What it is, and what it is not

- **It is** a personal tool: one copy per person, on accounts you own.
- **It is** read-only. It never writes to LinkedIn or your mailbox, and never
  sends anything to anybody except the one summary to you.
- **It is not** a CRM, an outreach or auto-reply tool, or a hosted service.
  Never run one copy for several people: the database has a single owner and
  no separation between users.

## Who it is for

Anyone who juggles many one-to-one conversations across LinkedIn and e-mail and
keeps losing track of who is waiting for an answer: job seekers, founders
raising money, freelancers, people doing sales or partnership outreach.

## How it works

```
LinkedIn messages ─────────┐
Gmail, Outlook or any      │
  IMAP mailbox ────────────┼─▶ collect ─▶ drop noise ─▶ group by person ─▶ Claude judges each person
Outlook calendar ──────────┘                                                        │
                                                                                    ▼
                                                           your Supabase database (checked before saving)
                                                                        │
                                                        ┌───────────────┴───────────────┐
                                                        ▼                               ▼
                                               private dashboard              morning summary e-mail
```

Everything runs once a day on GitHub Actions in your own private copy, on your
own Claude subscription, so your computer can be off. There is no server of its
own: the backend is a command-line tool (`tracker`) that a Claude Code session
runs step by step, following
[`.claude/commands/daily-run.md`](./.claude/commands/daily-run.md). A Claude
cloud routine can run the same recipe instead (the alternative route, for
Outlook-only set-ups). The design is described in
[`docs/architecture.md`](./docs/architecture.md).

## What you need

| Item | What it is used for | Cost |
|------|---------------------|------|
| A [Supabase](https://supabase.com) project | The database and the dashboard sign-in | Free plan |
| A [Vercel](https://vercel.com) account | Publishing the dashboard | Hobby plan, free for personal, non-commercial use |
| A paid Claude plan (Pro, Max or Team) | The Claude Code session that runs everything and does the judging, through a key made with `claude setup-token` | Your existing subscription; no separate API key |
| A GitHub account | Your private copy of the code, and GitHub Actions, which starts the run every day | Free (2,000 Actions minutes a month for private repositories; a month of runs uses about 150–300) |
| At least one mailbox: Gmail, Outlook.com/Hotmail, iCloud, Yahoo, Fastmail or any IMAP mailbox | The mail that is read (read-only). Gmail and the others need an app password, which also sends you the summary; Outlook needs a one-time sign-in | Free (Fastmail: a paid plan above Basic) |
| *Optional:* a Microsoft personal account | The calendar, which is read from Outlook only for now | Free |
| *Only for the alternative route:* a Gmail account connected to Claude | Sending the summary from a Claude cloud routine, when you read Outlook alone | Free |
| A LinkedIn developer app (optional) | Reading your LinkedIn messages | Free, but see the region limit below |

Setting it up takes roughly an hour, most of it creating accounts and copying
values from one screen to another.

### LinkedIn: only in the EEA and Switzerland

LinkedIn's official API for exporting your own messages (Member Data
Portability) is available only to members located in the European Economic
Area and Switzerland. Elsewhere, leave LinkedIn out: everything else works
without it.

LinkedIn's copy of your messages also runs one to two days behind, so a
LinkedIn message reaches Threadline a day or two after you receive it. Mail and
calendar entries are read as they are at the moment of the run.

## Quick start

1. Follow [`docs/setup-your-accounts.md`](./docs/setup-your-accounts.md) to
   create the accounts and collect the values Threadline needs.
2. Install [uv](https://docs.astral.sh/uv/), then install the backend:

   ```bash
   cd backend
   uv sync
   ```

3. Run the setup wizard, which asks for those values and writes your `.env`,
   then check that everything is reachable:

   ```bash
   uv run tracker setup
   uv run tracker doctor
   ```

4. The wizard ends with the daily time (`tracker setup schedule`), your
   settings on GitHub (`tracker setup github`) and the dashboard's Refresh now
   button (`tracker setup refresh`). Then start the first run by hand on
   GitHub (**Actions → Threadline run → Run workflow**), as the setup guide
   describes.

Day-to-day operation — what to do when something fails, renewing the LinkedIn
key and the yearly Claude key, redoing the Microsoft sign-in, changing the time,
pausing and resuming — is in
[`docs/operations.md`](./docs/operations.md).

## Command reference

Run every command from the `backend/` folder as `uv run tracker …`.
`uv run tracker --help`, or `--help` after any command, shows the same
information.

### Setup and checks

| Command | What it does |
|---------|--------------|
| `tracker setup` | Guided setup that writes your `.env` |
| `tracker setup mailbox` | Choose the mailbox to read; for Gmail and other IMAP mailboxes, check an app password live and store it encrypted |
| `tracker setup schedule` | Write the daily time and time zone into the GitHub workflow; commit and push it only after a yes |
| `tracker setup github` | Save your settings and the Claude key as your repository's Actions secrets and variables (with `gh`), or list the names to add by hand |
| `tracker setup refresh` | Switch on the dashboard's Refresh now button: deploy the `refresh-now` function and its settings through Supabase's Management API, with a GitHub key that can only start your workflow |
| `tracker setup cloud` | The alternative route: what a Claude cloud routine needs |
| `tracker doctor` | Check that every account and setting is in order |
| `tracker healthcheck` | Check the configuration, the database and the secret store |
| `tracker sample load` | Write made-up sample records; running it twice changes nothing |
| `tracker sample clear` | Remove the made-up sample records, leaving real data untouched |

### Collecting

| Command | What it does |
|---------|--------------|
| `tracker microsoft login` | Sign in to the mailbox once; the key then renews itself |
| `tracker microsoft forget` | Remove the stored mailbox key, so the next run needs a new sign-in |
| `tracker collect linkedin [--since YYYY-MM-DD] [--show-folders]` | Read the LinkedIn archive and store the recent conversations; `--show-folders` also prints the distinct LinkedIn folder values |
| `tracker collect email [--since YYYY-MM-DD \| --refresh]` | Read every mailbox you set up (Outlook, Gmail…) and store the conversations worth keeping; `--refresh` reads only what is new since the mailboxes were last read successfully |
| `tracker collect calendar` | Read the Outlook calendar and store the meetings with other people |
| `tracker collect all [--since YYYY-MM-DD \| --refresh] [--record] [--run ID]` | Read every source at the same time, then store them one after the other. `--record` also records each source as its step of the run and carries on past a source that failed — this is the command the daily run uses |
| `tracker people list` | Show everybody the collectors have found, most recent first |
| `tracker people merge` | Join the records you have confirmed are one person |
| `tracker people link` | Ask about records that look like one person or one opportunity |
| `tracker people untangle` | Split up records that were really a shared sender, such as a hiring system |

Without `--since`, the first run reads the last 30 days and later runs continue
from the last successful run.

### Assessment

| Command | What it does |
|---------|--------------|
| `tracker ai export [--limit N] [--batches DIR]` | Write one file per group of people who still need a verdict |
| `tracker ai import [--results DIR] [--batches DIR]` | Check the verdict files, save the ones that pass, and delete the files it applied |
| `tracker ai status [--results DIR] [--batches DIR]` | Show what is waiting: people to judge, files to import, questions to answer |
| `tracker ai clean` | Remove every exchanged file, including batches that were never answered |

The judging itself happens in Claude Code with the `/assess` recipe
([`.claude/commands/assess.md`](./.claude/commands/assess.md)); no command
calls an AI service.

### Profile

| Command | What it does |
|---------|--------------|
| `tracker profile choose [--preset NAME]` | Pick a preset, keep the suggested categories you use and add your own; saved to the database |
| `tracker profile check [--file PATH \| --preset NAME]` | Check your profile (or a shipped preset) and print its suggested categories and stage labels; changes nothing |
| `tracker profile apply [--file PATH] [--categories]` | Save the stage labels and suggestions and rebuild `docs/assessment-guide.md` from your categories; `--categories` also replaces your categories with the file's list |

See [`docs/customising.md`](./docs/customising.md).

### The daily run

| Command | What it does |
|---------|--------------|
| `tracker run start [--trigger github\|cloud\|refresh\|mac\|manual]` | Open today's run and print its identifier (default trigger: `cloud`) |
| `tracker run step --step STEP --result success\|failed [--found N] [--new N] [--error-code CODE] [--error-detail TEXT] [--run ID]` | Record what one part of the run did. `STEP` is `collect_linkedin`, `collect_email`, `collect_calendar`, `assess` or `summary_email` |
| `tracker run finish [--run ID]` | Close the run with the status its steps add up to |
| `tracker summary build [--out PATH] [--run ID]` | Write the morning summary to a file, ready to send, and say how it is sent (`delivery: smtp` or `gmail_connector`) |
| `tracker summary send [--file PATH] [--run ID]` | Send that file from your own mailbox by SMTP, exactly as built and only to your configured recipient, and record the step |

The workflow [`.github/workflows/threadline-run.yml`](./.github/workflows/threadline-run.yml)
runs `/daily-run` every day, or by hand with mode `daily` or `refresh` (new
messages only, no e-mail). Without its secrets it finishes green and does
nothing.

## Customising

Choose your categories on the dashboard's **Settings** page, or in the terminal
with `tracker profile choose`. Categories, presets and wording are explained in
[`docs/customising.md`](./docs/customising.md). What every status and
waiting-on value means is defined in
[`docs/assessment-guide.md`](./docs/assessment-guide.md).

## Privacy and security

- Everything lives in accounts you own: your database, your dashboard, your
  GitHub repository and your Claude subscription. Nothing is sent to the
  project's authors. The Claude key goes only into your own repository's
  secrets; Threadline never stores it.
- The mailbox and calendar are read with read-only permissions. Nothing is
  ever written to LinkedIn or the mailbox.
- Message text is treated as untrusted input. Only a restricted helper with no
  shell and no network reads it, and its answers are validated strictly before
  anything is saved, so an e-mail saying "ignore your instructions" cannot act.
- Conversations judged to be noise keep no subject and no text. The files that
  carry message text to the AI step are deleted once their verdicts are saved.
- The dashboard's public key reads nothing on its own: the database only
  answers the one signed-in owner.

The full model — what is stored where and how untrusted text is contained —
is in [`SECURITY.md`](./SECURITY.md). Report vulnerabilities privately through
GitHub, as described there.

## Folder map

| Folder | What is in it |
|--------|---------------|
| `backend/` | The Python jobs and the `tracker` command-line tool |
| `backend/tests/` | Unit tests; they never touch the network |
| `frontend/` | The dashboard (Vite, React, TypeScript) |
| `supabase/migrations/` | The database structure and its access rules, one file per change |
| `.claude/` | The daily-run and assessment recipes, the assessor helper and the session's permissions |
| `.github/workflows/` | The checks every change must pass, and `threadline-run.yml`, the daily run |
| `docs/` | Setup, operations, architecture, the assessment guide and the coding standards |

## Development

```bash
cd backend
uv sync
uv run ruff check .
uv run pyright
uv run pytest -q

cd ../frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

The home-screen icons in `frontend/public/icons/` are drawn by
`npm run icons` from the logo and the colour tokens; run it again after
changing either, and commit the new files.

All of these run in CI on every push and pull request. See
[`CONTRIBUTING.md`](./CONTRIBUTING.md) before opening a pull request, and
[`CLAUDE.md`](./CLAUDE.md) for the engineering standards.

## Licence

[MIT](./LICENSE) © 2026 roccoterr97
