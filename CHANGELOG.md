# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- One Supabase access token for the whole `tracker setup` run. It is asked
  once (Supabase's token page opens; name it "Threadline set-up", shortest
  expiry), checked with a read of your organizations that changes nothing,
  kept in memory until the run ends and never written to `.env`, logged or
  shown. `tracker setup supabase` now uses it to create the project (or reuse
  one of yours), in the region group nearest your time zone, with a generated
  database password that is never kept; it waits until Supabase reports the
  project healthy, reads its publishable and secret keys (creating them if
  the project has none) and saves the address and both keys as before. Typing
  an existing project's address and keys by hand is still offered.
- A one-line install. On macOS or Linux,
  `curl -LsSf https://raw.githubusercontent.com/roccoterr97/threadline/main/install.sh | sh`;
  on Windows, in PowerShell,
  `irm https://raw.githubusercontent.com/roccoterr97/threadline/main/install.ps1 | iex`.
  It installs uv and the GitHub CLI when they are missing (Homebrew on a Mac,
  winget on Windows, apt or dnf on Linux), signs you in to GitHub in the
  browser, makes your private copy from the template, downloads it to
  `~/threadline`, and starts `uv run tracker setup`. Pasting the line again
  carries on where it stopped and reuses a copy that already exists.
- `tracker setup dashboard` publishes the dashboard on Netlify by itself, free
  and with nothing to install: it downloads the ready-made dashboard from the
  template's GitHub Release, checks its SHA-256, adds a `config.js` holding
  only the project address and the publishable key, asks for a Netlify
  personal access token (pasted hidden, checked with one harmless read, never
  saved), creates a site under a free random name, uploads it, waits until it
  is live and checks the address opens. It then sets Supabase's Site URL and
  Redirect URLs itself with the run's Supabase token, opening the URL
  Configuration page only if Supabase refuses. The site is remembered as
  `NETLIFY_SITE_ID` in `.env` (not a secret), so running the step again
  publishes the newest dashboard to the same address. Contributors with
  Node.js 22 can publish a local build instead; hosting it elsewhere still
  works by typing its address.
- `.github/workflows/dashboard-release.yml`: every push to `main` of the
  public template builds the dashboard once and publishes
  `dashboard.zip` and `dashboard.zip.sha256` on the rolling `latest` release.
- Notes you type on a person: on a person's page, "Your notes" keeps what no
  message says ("met at the Lyon fair, prefers calls after 4pm"), newest
  first with the day each was written and the day it was last changed.
  Notes are for you alone — the assistant does not read them and they are not
  in the morning e-mail — and they stay with the person when two records are
  joined into one. Deleting a note asks first. Migration
  `0016_person_notes.sql`, applied by `tracker setup database`; the demo has
  two notes on Maya Lindqvist. A dashboard whose database does not have the
  table yet says which command to run instead of breaking.
- An Organisations page on the dashboard: the same people grouped by the
  organisation they are listed under, with how many people are there, where
  things stand with them as a whole (overdue, your turn, time to chase,
  waiting on them) and the most recent contact, those needing you first.
  Opening an organisation lists its people; people with no organisation on
  record are gathered under "No organisation". The page sits next to People
  in the menu; on a phone a People / Organisations switch at the top of both
  pages leads between them. Every way back from a person returns to the
  list it was opened from.
- The on-time morning start. GitHub often started the scheduled daily run five
  or six hours late; now the owner's Supabase project starts it at its time. A
  pg_cron job (migration `0017_daily_start`) calls the `refresh-now` function's
  new scheduled path, `…/refresh-now/daily-start`, every 15 minutes with a
  shared key kept in Vault; once the owner's daily time has passed in the
  owner's time zone, the function asks GitHub to start the workflow in daily
  mode. It starts at most one run per owner-local day: the day is claimed in
  the new `daily_starts` table (one row per date, so two overlapping calls
  cannot both start one), a daily run already in `run_logs` or already on
  GitHub that day counts as done, and a refused or failed request gives the
  day back so the next call retries. It does nothing for owners on the Claude
  cloud routine. GitHub's own schedule stays as a backup: a run it starts
  stops early when a daily run of the owner's day already started (or
  finished well), and the once-a-day e-mail rule remains the last net.
  `tracker setup refresh`, one of the extras, switches it on (a fresh key in
  the function's settings and in Vault, the timer made sure of),
  `tracker setup schedule` and `tracker setup timezone` keep the daily time in
  the database in step with the workflow, and `tracker doctor` gains an
  **On-time morning start** line.
  Free on Supabase's free plan: pg_cron, pg_net and Vault are built in.

### Changed

- `tracker setup database` and `tracker setup refresh` use the run's Supabase
  token instead of asking for their own, and `tracker setup login` switches
  sign-ups off through Supabase's Management API, opening the settings page
  only if Supabase refuses. A token that may not apply the structure now
  falls back to the SQL editor rather than stopping.
- `tracker setup` runs only the core steps, the ones the first morning
  e-mail needs: supabase, encryption, database, login, categories, timezone,
  mailbox, microsoft, dashboard, schedule and github. It ends by saying the
  first run has started (or which page starts it), that the summary e-mail
  arrives in about ten minutes and then every day at the time and zone in the
  workflow, and how to add the extras later; the final doctor report stays.
  The optional steps, LinkedIn (EEA and Switzerland only), the Refresh now
  button and the Claude cloud route, move to the new `tracker setup extras`,
  which runs them in that order, each skippable. `tracker setup linkedin`,
  `refresh` and `cloud` still run one step alone.
- `tracker setup github` finishes the job itself. With the GitHub CLI signed
  in, after saving the secrets and variables it makes sure Actions and the
  `threadline-run.yml` workflow are switched on in your copy, then starts the
  first daily run after one yes (the default) and prints the page where the
  run can be watched; the summary e-mail arrives about ten minutes later.
  When GitHub refuses (codes `workflow_not_enabled`, `workflow_not_started`),
  or without the CLI, it names the page where 'Run workflow' is pressed by
  hand instead. Opening the Actions tab and pressing the button yourself is
  no longer part of the set-up.
- The set-up runs on Windows. The clipboard uses `clip` there (and `wl-copy`,
  `xclip` or `xsel` on Linux, `pbcopy` on a Mac, whichever works first); the
  computer's time zone is read with `tzutil` and turned into its standard
  name; `.env` is written the same way everywhere, and a disk that keeps no
  file permissions no longer stops it; `gh` and `git` are found as `gh.exe`
  and `git.exe` and read as UTF-8. The set-up's wording no longer assumes a
  Mac ("a terminal" and "Enter", the GitHub CLI's own download page). Windows
  installs the small `tzdata` package, which Python needs there for time-zone
  names. CI runs the backend checks on Windows too.
- The dashboard reads its Supabase address and publishable key from a
  `config.js` beside it when there is one, and from the `VITE_` values
  compiled in otherwise, so one prebuilt dashboard serves every owner while
  `npm run dev`, Vercel projects and the demo work as before. A build without
  settings also writes Netlify's `_headers` and `_redirects` from the same
  rules as `frontend/vercel.json`, and a test keeps the two in step.
- `tracker doctor` no longer assumes the dashboard is on Vercel: a dashboard
  that does not open points to `tracker setup dashboard`.
- `tracker setup` stops at the dashboard step when the dashboard is not
  published (no to Netlify, and no to another host), instead of carrying on
  to steps that need it; running `uv run tracker setup` again carries on from
  there. A stopped run's last line names the command to run again:
  `uv run tracker setup` for the core steps, `uv run tracker setup extras`
  for the extras.
- `tracker setup github` says plainly when the run on GitHub cannot e-mail
  the morning summary (Outlook alone, or `SUMMARY_DELIVERY=gmail_connector`)
  and names the two ways out.
- The `ai export/import/status` and `summary build/send` help shows default
  files as `work/… in the project folder` instead of the machine's full path.
- Claude's project settings (`.claude/settings.json`) ask before a `curl`
  download instead of refusing it, so the set-up recipe can install `uv` and
  the Claude command-line tool from the project folder; `wget` stays refused,
  and the daily run on GitHub, which cannot ask, still refuses both.
- The daily run asks the database less often. Tidying people no longer looks
  up every pair an earlier merge already joined; saving the assessment looks a
  file's organisations up together and reads the categories once; a collector
  reads the whole people list only when somebody new turns up; and the calendar
  reads a shared calendar's invitation threads, and who is on record for your
  own interview entries, once instead of once per entry. The same rows are
  stored and the same lines printed.
- The database is asked less often. Reading every matching row used to end
  with one more request, sent only to see it come back empty. The first request
  now also asks how many rows match, and the reading stops once that many have
  arrived, so a read that fits in one answer costs one request. On a made-up
  morning of 300 people and 400 threads the daily run went from 283 database
  requests to 197. A page the server cut short is still read past, and an
  answer that carries no total is still read until an empty page. The same
  rows are read, in the same order.

### Fixed

- A command that fails because a setting is missing or wrong (such as
  `tracker healthcheck` without a `.env`) now also prints the doctor's
  one-line fix.
- `tracker collect email --help` no longer mentions `--record`, which only
  `collect all` has.
- The set-up's wording no longer assumes a Mac (⌘ + N, Homebrew) and names
  the real place of `.env` (the top folder of the project, not
  `backend/.env`); the database step says which access the Supabase token
  needs; the Supabase step says a Project ID is enough.
- On a phone, the "how many people in each category have each status" grid
  now says when it scrolls sideways and fades its hidden edge, instead of
  cutting the last column off without a hint.
- A long meeting title in "Coming up" no longer ends in "…" on a laptop: the
  card widens for it, and on a phone the title wraps inside the card.
- On a person's page the menu now marks People (or Organisations, when the
  person was opened from an organisation's page), as every other page marks
  its own item.
- Choosing another preset no longer fails when a hidden category still has a
  name the new list uses (job search to fundraising with someone filed as
  "Investor"): the hidden one becomes "Investor (2)" and keeps its people. A
  list that names two categories alike is refused before anything changes, the
  preset is remembered only once the categories are saved, and
  `tracker profile choose` refuses a group name you already have.
- `tracker setup database` and `tracker doctor` now see whether
  `0015_category_names.sql` is applied, so a database at 0014 is offered it. A
  database at 0006 or 0010 is now also offered 0007 or 0011.
- For another mailbox provider, a sending (SMTP) server that will not sign in
  no longer throws away the checked app password: the mailbox is saved first,
  and you can carry on without the sending server and add it later with
  `tracker setup mailbox`. A sending server saved for a different mailbox is
  removed rather than used with the new one.
- `tracker setup refresh` only uses a private GitHub repository you administer
  as your copy, never the public template; when that cannot be checked, it is
  switched on only on a typed yes.
- A run interrupted for hours (a Mac that slept) no longer loses its
  assessment: the verdicts are saved even when the run can no longer be
  recorded, and `run finish --clean` keeps the exchanged files when the run
  could not be closed.
- A daily run and a refresh no longer cross: a GitHub hiccup is never read as
  "nothing else is going" (a refresh stops, the daily run keeps asking and
  goes ahead once its wait is up), each lookup is cut off after 30 seconds,
  and a refresh can close only a refresh, the daily run only its own run.
- The morning summary is sent once even when recording that it went fails. On
  the Gmail-connector route, a summary already recorded as sent is not built
  again for the same run.
- When a mailbox holds more new mail than is read at once, or one of several
  mailboxes cannot be read, the mail that was read is judged the same morning,
  the summary and the run page say so in plain words, and the next read does
  not skip the part left unread.
- Two Refresh now presses a moment apart: the one that loses is told a refresh
  is starting, or starts it itself when the first could not, instead of being
  told to wait ten minutes.
- The daily recipe says one thing about a run that is not open, and about
  verdicts that were saved without their step being recorded.
- The dashboard keeps your place: Back, Forward and a reload return to where
  you were on a page (as close as possible when the list got shorter), a page
  opened fresh starts at the top, and "Back to people" and hiding a person
  return to the list with your filters and sort.
- A hidden person leaves the list at once. A suggested category whose name
  another category has is no longer offered.
- A failed save is always unmissable: a failed category move, a failed hide
  and a failed undo each take the keyboard and scroll into view. A saved
  answer on the review page no longer takes the keyboard away from the list.

### Documentation

- A fresh-eyes walk through the guides, from the download to the first run:
  the README says how to get the code before trying the demo, describes
  every supported mailbox, points the Quick start into the guide in order,
  marks `gh` as recommended and moves `tracker healthcheck` to the daily-run
  table. The set-up guide gains "Words used here" and "On Linux" notes, the
  gh installer instead of Homebrew, the stop-and-carry-on flow, where
  Vercel's two values come from, the Outlook-only warning, git's "Please
  tell me who you are", and the dashboard's own words for a run's result.
  The operations page names results as the dashboard shows them, matches
  the schedule step, gains "Renew the Refresh now key" and says which folder
  each command runs in; the Refresh now and demo pages do the same.
- The README shows the dashboard: the people list (light and dark) under the
  opening lines, and a "What it looks like" section with the home page, the
  review questions, one person's timeline and the list on a phone, all taken
  from the demo (`docs/images/`).
- The set-up recipe Claude follows (`.claude/commands/setup.md`) survives a
  computer with nothing on it: it checks the tools as the Terminal sees them
  and installs the Claude command-line tool when only the desktop app is
  there (the app keeps its own copy where the Terminal cannot find it, so
  `claude setup-token` would answer "command not found"); it runs
  `gh auth setup-git` and gives git a name and GitHub's no-reply address, so
  the schedule step can save its change; it follows the first run by number
  (`gh run watch` alone refuses without a terminal); it offers gh's `.pkg`
  installer on a Mac without Homebrew; and it waits for the final check's
  line rather than the page's "All done", which is never echoed to it.
  `setup-with-claude.md` names the third helper.

## [0.2.0] - 2026-10-01

### Added

- A set-up that Claude runs for you: the recipe `/setup`
  (`.claude/commands/setup.md`) walks a non-technical person through the
  tools, their private copy, the three accounts, the guided set-up and the
  first run, with Claude doing every command and the person pasting keys only
  into the set-up page. [`docs/setup-with-claude.md`](docs/setup-with-claude.md)
  is the one sentence to paste into the Claude app; the README and the demo's
  "Set up your own" link now lead there first.
- `uv run tracker setup --browser` (also for a single step): the same
  questions asked on a page in your web browser instead of terminal prompts,
  with keys in hidden fields, a Continue button for every "press Return", a
  Stop-for-now link, and the final check shown on the page. The page is served
  to your computer only, on a random port, and every request must carry a key
  that only the opened page knows. The terminal still shows what is said and
  asked, never an answer, so whoever started the command can follow along. A
  page closed or left alone for fifteen minutes ends the set-up cleanly.

- The set-up's "press Enter" and "press Return" phrases now come from the
  terminal itself, so each step's wording reads right on the page too.
- `tracker setup refresh`, a set-up step right after `tracker setup github`
  that switches on the dashboard's Refresh now button with nothing to install:
  it opens GitHub's new-token page already filled in (Actions: Read and write),
  checks the token with one read of the workflow that starts nothing, saves
  the `refresh-now` function's settings and deploys it through Supabase's
  Management API with a scoped access token, then checks that the function
  turns away a caller with no sign-in. Neither key is shown or written to
  `.env`. `tracker doctor` gains a **Refresh now** line, and the dashboard,
  when it cannot reach the function, now names that command (and says
  "offline" only when the browser is).

- Categories you define: keep, rename, recolour, reorder, hide or add them on
  the dashboard's new Settings page, or with `tracker profile choose`.
- Five presets (job search, sales outreach, fundraising, freelance clients,
  networking) with suggested categories, stage wording, AI guidance and
  collection rules; `tracker profile check` and `tracker profile apply`.
- A categories step in the guided set-up (`tracker setup categories`), right
  after the dashboard login: pick a preset, keep or drop each suggestion, add
  your own, or skip it and keep the job-search categories.
- A demo of the dashboard (`npm run demo` in `frontend/`): invented sales
  outreach data, no accounts, nothing saved. Normal builds leave it out.
- Gmail, iCloud, Yahoo, Fastmail and any other IMAP mailbox as a mail source,
  read-only, with an app password checked live and stored encrypted in the
  database (`tracker setup mailbox`). New settings `MAIL_SOURCES`,
  `IMAP_PROVIDER`, `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`; a doctor line
  for the IMAP mailbox; a summary sentence naming the provider when it refuses
  the app password (code `mailbox_password_refused`); "Renew a mailbox app
  password" in `docs/operations.md`.
- GitHub Actions as the main way to run Threadline every day
  (`.github/workflows/threadline-run.yml`), on your own Claude subscription
  through the key `claude setup-token` makes. It runs on a daily schedule with
  a time zone, or by hand with mode `daily` or `refresh`; without its secrets
  it finishes green and does nothing.
- A refresh mode for an extra run between two mornings: new messages only
  (`tracker collect email --refresh`), no summary e-mail. Runs record the new
  triggers `github` and `refresh` (migration `0012_refresh_trigger.sql`).
- `tracker summary send`: the summary sent by SMTP from your own mailbox with
  its stored app password, exactly as built and only to your configured
  recipient. New settings `SUMMARY_DELIVERY`, `SMTP_HOST`, `SMTP_PORT`; a
  doctor line that signs in to the SMTP server without sending anything.
- Set-up steps `tracker setup schedule` (the daily time, written into the
  workflow) and `tracker setup github` (settings into the repository's Actions
  secrets and variables with `gh`, or a list of names to add by hand).
- "Renew the Claude key", "What a failed run looks like on GitHub" and GitHub's
  free minutes in `docs/operations.md`.

### Changed

- The daily run starts at 07:00 Paris time instead of 07:00 UTC.
  `uv run tracker setup schedule` sets your own time and zone.

- The daily run asks the database less often. Tidying people no longer looks
  up every pair an earlier merge already joined; saving the assessment looks a
  file's organisations up together and reads the categories once; a collector
  reads the whole people list only when somebody new turns up; and the calendar
  reads a shared calendar's invitation threads, and who is on record for your
  own interview entries, once instead of once per entry. The same rows are
  stored and the same lines printed.

- The daily run collects every source in one step. `tracker collect all
  --record` reads LinkedIn, the mailboxes and the calendar at the same time,
  stores them one after the other, records each as its own step of the run and
  carries on past a source that failed. The recipe used to run three collect
  commands and three `run step` commands in a row; `collect linkedin`,
  `collect email` and `collect calendar` still work by hand. `collect all`
  also takes `--refresh` and `--run`.
- The daily run takes fewer steps around the collection. `tracker run start
  --prepare` opens the run, runs the health check and applies the profile, and
  ends with `ready: yes` or `ready: no`; `tracker people tidy` is `people
  merge` followed by `people link`; `tracker run finish --clean` closes the run
  and removes the exchanged files. Each prints what the separate commands
  print, and a part that fails is printed with its code while the rest still
  runs. The separate commands still work by hand.
- The assessment records its own step. `tracker ai export --record` and
  `tracker ai import --record` record the `assess` step of the run, which the
  recipe used to do with a `run step` command; a second import in the same run
  adds to the step. `tracker ai export` also makes the directory the verdicts
  go in, so the `/assess` recipe no longer runs `mkdir`.
- Mailboxes are read faster. The threads of a mailbox, and the messages of a
  thread, are asked for together instead of one at a time, and two mailboxes
  are read at the same time. Outlook is sent at most three requests at once
  (Microsoft accepts four per mailbox); a Gmail or other IMAP mailbox still
  takes one command at a time on its one connection. The same messages are
  read and the same rows stored.
- A Gmail or other IMAP mailbox is read in fewer round trips. The bodies of a
  kept thread are fetched with one command per folder instead of one per
  message, and the folder that is already open is read first, so it is opened
  less often. On a made-up mailbox of 17 threads the body pass went from 48
  commands to 29. A connection that drops is reopened with its folder, even
  when it drops again while reopening. The same messages are read and the same
  rows stored; Outlook is read as before.
- `tracker doctor` runs its checks side by side, so the waits overlap instead
  of adding up. The report keeps its order.
- `tracker setup linkedin` walks a first connection through three stages —
  create the developer application, add the product, make the key — opening
  the right LinkedIn page at each one, and ends cleanly when LinkedIn does not
  offer the product to your profile. With a key already saved it is a renewal
  and goes straight to making a new key. The expiry date can be typed with the
  month's name (`24 Sep 2027`) as well as `YYYY-MM-DD`. The guide now says up
  front that LinkedIn is optional, depends on where your profile is located,
  and delivers messages a day or two late.

- The Claude cloud routine is now the alternative route, mainly for an owner
  who reads Outlook alone (Outlook.com does not let mail programs send with an
  app password). `tracker setup cloud` asks before it lists anything.
- The morning summary's "replied since" ignores refresh runs.

- Outlook is now optional: at least one mailbox is required, Outlook or IMAP.
  Without `MAIL_SOURCES` Outlook is read as before, so existing set-ups keep
  working unchanged. The calendar is still read from Outlook only; without
  Outlook it is reported as not configured. Every mailbox is recorded under the
  existing `collect_email` step, so no migration is needed.

- The product is now called Threadline ("Every conversation, one clear line."),
  formerly Conversation Tracker. The default summary subject prefix is
  `[Threadline]`; set `SUMMARY_SUBJECT_PREFIX` to keep the old `[Tracker]`. The
  `tracker` command and package keep their names.
- The status `in_hiring_process` is now `in_process`; its on-screen words come
  from the preset. Migrations `0009_categories.sql` and
  `0010_status_in_process.sql` must be applied.
- `docs/assessment-guide.md` is generated from
  `profile/assessment-guide.template.md`, the preset and your categories.

### Fixed

- Morning e-mail: a reply is no longer left out of every summary when the
  previous morning's e-mail did not go out, and a busy day of Refresh now
  presses no longer shortens the "replied" window. Running the morning a second
  time the same day (GitHub's "Re-run job", or starting it by hand) no longer
  sends a second e-mail: the run says "summary skipped" and the Runs page
  "not sent", unless `--send-again` asks for another copy on purpose.

- Set-up: one Ctrl-C now stops it at once, before anything else is saved.
  `.env` is made readable by you alone on every write, not only when it is
  created. A name written twice in `.env` gets the new value on every line,
  quotes are read the way the app reads them, and a value holding ` #` or edge
  spaces is quoted so it is not cut short. Changing your time zone also moves
  the daily run's `timezone` line, so the run keeps its hour. The `/setup`
  recipe now names the right `.env` file and says plainly that Claude sees the
  set-up page's address.

- `tracker sample load` moves the sample dates to today, so the sample
  dashboard no longer looks weeks old and overdue.

- Demo: answering a "part of your outreach?" question now adds or removes the
  person, as in the real app; "Refresh now" no longer claims new messages it
  never adds; the "same person?" question names two records.

- CI: the secret scan no longer fails on the first push of a new copy, whose
  first commit has no parent.

- Collecting: a conversation the assistant or you kept no longer loses its
  stored text when a later message makes the rules call it noise, and a
  message that could not be read again never blanks out stored text. A noise
  conversation keeps its earliest and latest dates. In LinkedIn group threads a
  name with a comma ("Jane Doe, CFA") no longer moves every name onto the wrong
  person; a name that cannot be paired is filled in from that person's own
  reply. The Microsoft key is fetched again for every retry, so a long retry no
  longer ends with a false "sign in again".

- People and verdicts: merging two records no longer fails in the database or
  loses "same person?" answers, answers chained through one record join all
  three, and a merge never leaves the same question twice. A company record is
  never joined to someone you said is a different person. A "noise" verdict no
  longer overrules your own corrections: the person stays on your list and you
  are asked. A verdict never undoes a "not relevant" you gave after the export.
  Paged reads no longer skip or repeat rows that share a timestamp.

- Dashboard: "yesterday" means the previous calendar day; due dates no longer
  show a day early west of Greenwich; a failed review answer brings back only
  its own card; "Coming up" never links to a person who is not on your list;
  saving a blank correction removes it; the headline counters wait for the
  data instead of showing 0.

- The Microsoft sign-in key is renewed once when several requests find it
  expired at the same moment. Each renewal replaces the stored key, so two
  under way together could have saved one that was not the last one issued.

- `tracker setup database` no longer stops at the third file: Supabase names
  each applied file after the current second, so files are now sent at least
  1.5 seconds apart, and a refused file is sent once more before the set-up
  switches to the SQL editor. Supabase's own reason for a refusal is logged and
  shown in one line. In the SQL editor route, the set-up now checks after each
  Return that the file really ran, and asks for the same file again if not.

- The guided set-up now asks for your time zone (`tracker setup timezone`),
  right after the categories, offering the one your computer uses instead of
  leaving UTC. It also asks, optionally, for the name you go by
  (`OWNER_DISPLAY_NAME`). The daily time is read in that zone, and
  `OWNER_TIME_ZONE` goes to GitHub as a variable with the other settings.

- `tracker setup github` no longer assumes a GitHub copy exists. It reads the
  folder's `origin` link and checks it with `gh repo view`; without a copy it
  says so in two sentences and, after an explicit yes and only when `gh` is
  signed in, creates a private one (`gh repo create … --private --source .
  --remote origin --push`), or else gives the "Use this template → Private"
  steps and stops. `tracker setup schedule` only offers to push when there is a
  copy to push to; otherwise it offers to commit the change so it goes up with
  the copy. The `claude setup-token` instruction says where to run it and what
  the key looks like. The `git` lines the set-up prints work from any folder of
  the project, and the guide says once, with a check, where to type the
  `uv run tracker` commands.
- The Mac route in `docs/operations.md` says to accept Claude Code's "trust
  this folder" question once before the first unattended run.

- A run that died part-way (for example, GitHub stopped it) no longer stays
  "running" for ever. When `tracker run start` opens a new run, every earlier
  run still running that started more than three hours ago is closed as
  failed, with a failed row on the step it never finished and the code
  `run_interrupted`. A run that recorded every step and only missed its
  closing keeps the status its steps add up to. The dashboard's Runs page and
  the next morning summary say in plain English that the run was interrupted,
  and the summary's "replied since" no longer counts from an interrupted run.
  No migration is needed. "Refresh now" still treats a run younger than 30
  minutes as in progress.

- The database check now handles the update to the Refresh now trigger
  correctly.
- A run can no longer overwrite what a previous run recorded.
- Time zone names are accepted in any letter case (`europe/rome` is saved as
  `Europe/Rome`).
- Large mailboxes are now read reliably, in smaller pieces.
- Mailboxes from other providers ("other") can now send the morning summary:
  the mailbox step asks for the sending server (SMTP host, and port 465 or
  587) and signs in to it once, sending nothing, so a wrong server shows up
  during set-up. It saves `SMTP_HOST` and `SMTP_PORT`; choosing a known
  provider empties them again.
- The set-up now only ever saves settings into your own private copy on
  GitHub: with `gh` signed in, only a private repository you administer
  counts, never the project you copied it from.
- Wrong mail server names or ports give a clearer error that says what to
  check.
- Refresh now can no longer start two runs at once: two quick presses start
  one run (migration `0014_refresh_cooldown.sql`, applied by
  `tracker setup database`).
- Daily runs and refreshes queue separately on GitHub, so a refresh pressed
  while another is going can no longer drop the daily run waiting behind it.
  The daily run waits for a refresh in progress; a refresh steps aside while a
  daily run is going. The workflow now also has `actions: read` to see this.
- Settings emptied in `.env` but still saved on GitHub are listed the next
  time `tracker setup github` saves with `gh`, and deleted there after one yes,
  instead of staying there.
- The morning summary e-mail is no longer sent twice.
- The demo: signing out and hiding a person no longer leave you on a page with
  nothing to click.
- Two categories can no longer share a name or a group name, whatever the
  capitals: the dashboard refuses the second one and says which name clashed,
  and the database refuses it too (migration `0015_category_names.sql`, which
  first adds " (2)" to any name that already clashes). The dashboard also
  asks before it removes a category. The reserved category's group name is
  now "Not known", like its name.
- Clearer wording, colours, page titles and accessibility on the dashboard.

### Security

- Private vulnerability reporting is switched on for the repository; the
  steps (and a fallback) are in `SECURITY.md`.

### Documentation

- The setup guide and the README list every prerequisite up front (Mac or
  Linux, a Claude plan and its usage limits, Claude Code with a
  `claude --version` check, GitHub and the optional GitHub CLI, and the
  optional Node.js and Azure pieces), explain how to download your copy with
  `gh auth login`, give the order of the wizard's steps (answer "no" at the
  dashboard question the first time) and use one set-up time. The README
  command table lists every `tracker setup <step>` and `--guide`. The cloud
  variable list, placeholders (`<project-id>`) and `.env.example` headings are
  consistent, and the demo-site page explains what a fork changes.

## [0.1.0] - 2026-09-29

### Added

- First public release.
- Daily collection of LinkedIn messages (official data portability API), a
  Microsoft personal mailbox and its calendar, with noise filtered out and
  conversations grouped by person.
- Assessment by Claude inside a scheduled Claude Code session: status, who owes
  whom a reply, next action and due date, validated strictly before it is saved.
- Private dashboard (React, served as a static site) and a morning summary
  e-mail built entirely by Python.
- `tracker` command-line tool for collecting, assessing, recording runs and
  building the summary.
- Security policy, contribution guide, code of conduct, issue and pull request
  templates, and continuous integration with a secret scan.
