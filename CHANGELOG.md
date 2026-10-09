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
- CI now checks the installers without running them: `shellcheck install.sh` on
  Linux, and a PowerShell syntax check of `install.ps1` on Windows (in both
  PowerShell 7 and Windows PowerShell 5.1). Tests run `sh -n` on the installer
  and check its GitHub tool version comparison, and a Windows-only test checks
  that the computer's real `tzutil` answer maps to a known time zone.

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

### Fixed

- A harmless warning from git no longer makes the set-up think the workflow
  file has unsaved changes, and a copy with nothing on GitHub to compare with
  is no longer nagged to push. The set-up reads git's answer only for these
  checks, and uses what git printed as errors only to explain a failure. When
  the branch tracks nothing, it compares with the copy's default branch on
  GitHub.
- The Claude cloud route no longer offers to switch the GitHub daily run off
  as a default yes before the routine exists. The answer now defaults to no,
  and the step says to switch it off with
  `gh workflow disable threadline-run.yml` once the routine has run once and
  its e-mail arrived (or to answer yes if it already runs).
- The dashboard step tells a missing GitHub CLI apart from one that is not
  signed in. Missing, it says where to install it
  (<https://cli.github.com>), to sign in with `gh auth login` and to run the
  step again; the local build is still offered when Node.js 22 or newer is
  there.
- Setting up with Claude Code (`/setup`) now signs GitHub in with the
  `workflow` permission, and tops it up when you were already signed in
  without it. A push GitHub refuses for lacking that permission is explained
  in one plain line with the command that adds it
  (`gh auth refresh -h github.com -s workflow`), instead of git's raw message.
- The time-zone step no longer offers a guess when the computer's zone cannot
  be read (for example a Windows zone name newer than the table, which was
  offered as `UTC` and silently moved the daily run's hour). It now says "I could
  not tell your time zone", offers no default and asks you to type one such as
  `Europe/Paris`, checking it as before. The Supabase region offer still falls
  back to the Americas.
- `tracker doctor` and a failed command say only "run 'uv run tracker setup'"
  on a computer; the "add the missing secrets" half is said on GitHub alone
  (`GITHUB_ACTIONS=true`), where it applies.
- A GitHub CLI older than 2.68 (before `gh attestation verify --source-ref`,
  which the dashboard check uses) now stops the set-up at the first use of `gh`, naming the version
  and <https://cli.github.com>, instead of failing at the last step.
- LinkedIn added or renewed with `tracker setup linkedin` (or `extras`) now
  reaches the daily run: right after saving, the set-up offers to send just
  those settings to GitHub, and otherwise prints `uv run tracker setup github`.
  Before, they stayed in `.env` and the run on GitHub never used them.
- The set-up no longer promises a summary e-mail it cannot send, or starts a
  first run that would do nothing. When GitHub has no mailbox with an app
  password to send from (Outlook alone), the GitHub step says so plainly,
  offers to connect a Gmail or other mailbox right then, and otherwise offers
  the first run with a default of no; the closing words then promise only the
  dashboard and name the two ways to get the e-mail. Without the Claude key on
  GitHub (an empty answer keeps the key already there, if any) the first run is
  not started and the step says to run `claude setup-token` and then
  `uv run tracker setup github`. Choosing the cloud route in the extras offers
  to switch the GitHub daily run off (`gh workflow disable`), so both routes do
  not run.
- A new daily time or time zone no longer stays on your computer when the
  upload to GitHub stops. The set-up now says what git said (its first error
  line, never a web address's sign-in), and when git has no name to put on the
  change it prints the two `git config --global` lines to run. Running the
  schedule, time zone or GitHub step again offers the upload whenever your
  computer has a daily time that GitHub does not, not only when the text just
  changed, so GitHub no longer silently keeps the old time.
- Someone the AI dropped as "not part of your search" now comes back when it
  matters. If you write to them, or they start a new conversation that is not
  obvious machine mail, they go back to "unsure" and the AI reads them again.
  Before, they stayed hidden for good. More mail from their side in a thread
  already dropped (another newsletter) does not bring it back, and what you
  decided yourself (hiding someone, a "no", a "yes", a correction) is never
  undone.
- Sending the summary no longer stops with an unexplained crash. An app
  password with a hidden character in it (such as a space pasted from a web
  page) is now reported as a refused app password, for sending and for
  reading the mailbox alike, so the summary points to the right fix. A
  summary file whose subject holds a line break or another control character
  is refused with a clear message instead of crashing, and that failure is
  recorded.
- "Replied since yesterday" now catches a reply that was only collected later.
  It used to compare when a reply was sent with when the previous run started,
  so a reply written before that run but collected after it (a mailbox that
  was down that morning) never appeared in any summary. It now also counts
  messages stored since the previous summary, as long as they were sent in the
  three days before it, so a first import of old mail still does not list
  everyone.
- A morning is no longer called "worked" when no summary went out or nothing
  was collected. A daily run that never recorded its summary e-mail (it could
  not be built, or sending it stopped on something unexpected), and any run
  that never recorded a collect step (for example when the health check
  failed), now closes as "Partly worked". A summary that cannot be built is
  recorded as a failed summary step, so the run page and the next summary
  say so.
- One odd e-mail can no longer stop the whole collection. A message whose
  `References` header named an identifier with a letter like "é" in it made
  the reader of a mailbox that is not Gmail (plain IMAP) crash while it looked
  up the rest of the thread, and nothing from any source was stored or
  recorded that day. Such an identifier is now left out of the thread lookup (the thread
  keeps the messages already seen), and if a source does stop on something
  unexpected, it is logged by its type, recorded as that source's failed step
  with the code `source_failed`, and the other sources carry on.
- Signing in with an address the dashboard does not belong to no longer says
  "Your session has ended". The database turns that account away (a 403), and
  the dashboard now says the account is not allowed and to sign in with the
  owner's address, instead of sending people round in circles to sign in again.
  Only a missing or expired session still reads as signed out.
- A failed update no longer wipes a page that was already showing. If the
  connection drops while you are away (a phone waking up on a poor signal, say),
  the people, run history, notes and the rest stay on screen and a short note
  says "Couldn't update just now. Showing what was loaded earlier." The full
  error box now appears only when there is nothing to show yet.
- A person's page now keeps the newest messages of a very long conversation
  (over 500), not the oldest. Before, the latest replies were the ones left
  out. When older messages are left out, a short note says so.
- Signing out now wipes the data the dashboard was holding in the browser's
  memory, so the next person to sign in on the same phone or computer cannot
  glimpse the previous person's list before their own loads. The same happens
  when a session simply expires.
- A dashboard tab or home-screen app left open now catches up when you come
  back to it. Before, a page left open from Monday still showed Monday's
  overdue badges, an old "last run" warning and meetings that had already
  happened under "Coming up" on Tuesday, until you reloaded by hand.
- The dashboard no longer stops at 500 people. Someone with more than that saw
  only the 500 most recent, so the counters, the status grid and the
  organisation pages were quietly too low. It now reads everyone, and if a list
  ever passes 5,000 people it says that older ones are left out.
- "Refresh now" no longer stays on "Refreshing..." with the button greyed out
  when the update never starts. After fifteen minutes it stops waiting, says so
  and points to the run history, and the button works again.
- The assistant that reads your conversations can now write files in one place
  only, the `work` folder where it leaves its answers. It could write
  anywhere, so a hostile message could in theory have talked it into changing
  Threadline's own code, which the next morning's run would then have run. On
  GitHub the run now also refuses writes to the code, the settings, the
  recipes and the workflow. The project no longer approves edits by default
  when you work in this folder with Claude Code; you will be asked, as usual.
- Joining two people ("yes, same person") no longer loses anything. The joined
  person is judged again with all their conversations, takes the stronger of
  the two relevance settings (so a never-judged LinkedIn "Erik" cannot hide the
  address that was already a meeting), and keeps both people's corrections:
  what you set on the person that stays wins, and the empty fields (note, due
  date) are filled from the other.
- A person you hide with "Not relevant" while the assistant is still reading
  stays hidden. The assistant's answer used to arrive afterwards and put them
  back on the list.
- A message that arrives while the assistant is still reading is no longer
  marked as read. A person is now recorded as assessed up to the newest
  message the assistant was actually given, so anything stored since is looked
  at on the next run. A leftover answer file that is older than the person's
  latest assessment is dropped instead of overwriting it.
- A LinkedIn profile and an e-mail address are no longer joined without asking
  when the same name is already on your list twice on one side. Threadline
  used to check the name only against the people it was collecting that
  morning, not against the ones it had stored, so a second "Marco Rossi" on
  LinkedIn could be joined to the wrong "Marco Rossi" by e-mail. It now asks
  "same person?" instead.
- When you correct who owes the next move to "me", the follow-up date is
  today, not five working days after the last message. The date used to be
  worked out from what the assistant had said, before your correction counted.
- The dashboard is easier to use on an iPhone. The header no longer runs off
  the screen on a tablet held upright: the menu moves to the bottom bar up to
  1024px wide, and the header menu starts from there. The filter and sort
  lists are set in 16px text, so Safari no longer zooms in when you tap them.
  A tap lands from anywhere on a person's or an organisation's card, and the
  "back" links, the "Open" links on the review page, the counts in the status
  grid and the logo are all at least 44px high. A long name, e-mail address
  or organisation without spaces wraps inside its card instead of widening
  the page. Taps act at once (no double-tap delay), a field focused near the
  bottom scrolls clear of the bottom bar, and turned sideways, the page and
  the bottom bar keep clear of the notch.
- The version in `backend/pyproject.toml` and `frontend/package.json` now
  matches the release (0.5.1 is the next), and the changelog has a heading for
  0.5.0 again instead of listing everything since 0.2.0 as unreleased.
- The demo's first line says the ZIP download is enough, so nobody makes a
  GitHub account just to look at it.
- Running `tracker setup supabase` again after it stopped no longer makes a
  second project by accident. A project left behind (stopped with Ctrl-C, timed
  out, or created but not answering yet) is listed with its status, "running"
  or "still being set up", and pressing Enter now reuses the one named
  `threadline`. The messages for a stop, a timeout and a lost create request
  say that the project may already exist and to pick it from the list. The
  first checks on a project that was just created, and the database structure
  check, are repeated for about half a minute before they count as failed.
- `tracker setup database` no longer stops when your Supabase token can read
  but not change the database (Supabase answers "not allowed" when a file is
  sent). It says so and carries on with the hand-guided SQL editor, as it
  already did when the token could not even read.
- Running `tracker setup supabase` on its own when your `.env` already holds
  a project now says which project that is and keeps it by default, before
  asking for any token. Before, Enter went on to create a new project that was
  then thrown away because the saved one was kept. Answer no to switch
  projects; the new one replaces the saved one without a second question.
- `tracker setup supabase` no longer hides a paused project. Supabase pauses a
  free project after a week without use; the step now says "'name' is paused",
  how to restore it (open the project, click "Restore project", then run the
  step again) or that you can create a new one. A paused project is still not
  picked directly, because it takes a while to come back.
- `tracker setup login` no longer stops when Supabase has a server error or
  times out while switching sign-ups off; it falls back to the hand-guided
  settings page, as it already did when Supabase refused the change.
- The one-line installers download the uv installer to a file and check that the
  download worked before running it, so a failed download says "Could not
  download uv" instead of giving unrelated advice. The Windows installer does
  the same instead of piping the download into PowerShell.
- The macOS and Linux installer no longer installs a GitHub tool that is too old
  for the set-up. It checks the version it finds (2.68 or newer is needed) and
  updates an older one. On Linux it uses GitHub's own apt or dnf package source
  instead of the distribution's older package, and downloads the release into
  `~/.local/bin` when no package manager can be used. A Mac without Homebrew no
  longer stops at the GitHub tool: the installer downloads the right build for
  the Mac, checks it against the release's checksums and uses it.
- The Windows installer reads winget's exit code. A failed installation of Git
  or the GitHub tool now says "the installation of X did not finish (code N)"
  with the usual causes (the Windows approval was declined, or the network
  dropped) instead of "close this window". Without winget it says where to get
  "App Installer". An existing GitHub tool older than 2.68 is updated with
  winget.
- The one-line installers set up git for a new computer. When git has no name or
  e-mail yet, they set them from the GitHub account (the name, and GitHub's
  private `ID+login@users.noreply.github.com` address), say plainly what was
  set, and never change values that already exist. Before, the set-up stopped
  later with a vague message when it saved the daily-run time zone. The sign-in
  also asks for the `workflow` permission that saving that file needs, and a
  sign-in made without it is topped up with `gh auth refresh`.
- The one-line installers no longer reuse just any repository called `threadline`
  on your GitHub account. It must be private, you must be its admin, and it must
  have been made from the Threadline template (or contain `backend/pyproject.toml`).
  Otherwise the installer stops and names the cause and what to do, such as
  renaming the other repository.
- Running the one-line installer again after an earlier set-up no longer makes
  a second copy. If `~/tracker` (where an earlier version put the copy) holds
  Threadline and `~/threadline` does not exist, the installer says so and asks
  whether to use it (the default is yes). It also checks that the folder holds
  the `backend` part before going in, instead of failing on a missing folder.
- The Windows time-zone table is complete: all 140 zones Windows 10 and 11 offer
  (after the Unicode CLDR `windowsZones` table) instead of about 85, so zones
  such as Aleutian, Yukon, Sudan, Qyzylorda, Tonga and the "UTC-11 .. UTC+13"
  ones are no longer offered as `UTC`. When a Windows zone is still not in the
  table, its name is now logged (`windows_zone_unknown`) so the gap can be
  found.
- Publishing a dashboard you built yourself on Windows no longer fails with
  "npm not found": the build's programs are now looked up before they are
  started, so `npm.cmd` is found.
- The dashboard step no longer tells you a Netlify site name is taken when
  Netlify refused the new site for another reason (a limit, a bad field):
  only a refusal that blames the name makes it try another, and any other
  refusal is shown with Netlify's own words.
- When Supabase cannot be reached while the dashboard step sets its sign-in
  addresses, the step now shows the two values to type by hand instead of
  stopping after the dashboard was already published.
- Publishing the dashboard no longer wipes the other addresses on Supabase's
  Redirect URLs list (such as `http://localhost:5173/**` or an older host):
  the list is read first, the new dashboard address is added if it is
  missing, and the set-up says which address it added. The Site URL is still
  pointed at the new dashboard.
- The set-up now checks, right before uploading, that the dashboard holds
  its page, `config.js`, `_headers` and `_redirects`, and stops with a clear
  message if its own security-header files are missing or empty, instead of
  publishing a dashboard without them.
- The ready-made dashboard now carries a small `build-info.json` (the commit
  it was built from and the newest database file it expects), and `tracker
  setup dashboard` warns, in plain words, when the dashboard is newer than
  your copy of Threadline so you update your copy and database first. The
  file is read and not published.

### Security

- A hand-edited `NETLIFY_SITE_ID` in `.env` can no longer change which
  Netlify address the set-up calls: only a Netlify site identifier (a UUID
  or a plain site name) is accepted, anything else stops the step with a
  message saying what to fix.
- The dashboard step now also refuses an old-style (legacy) Supabase key
  that is really the service-role key when it is typed or saved where the
  public key belongs, so it can never be written into the published
  `config.js`.
- `tracker setup dashboard` no longer trusts the `_headers` and `_redirects`
  files inside the downloaded dashboard: it writes its own copies (the
  content security policy and the single-page fallback), so a tampered
  download cannot loosen what the page may load or where it may send a sign-
  in. A dashboard test fails if those copies drift from the rules the
  dashboard is built with.
- The workflow that builds the ready-made dashboard is split in two: a build
  job that installs the npm packages with read-only access and no GitHub
  token left on disk, and a separate publish job that can write the release
  but never installs or runs anything from the project. Every action it uses
  is pinned to a full commit.
- The ready-made dashboard is now checked for who built it, not only for
  damage: the release workflow signs a build-provenance statement for
  `dashboard.zip`, and `tracker setup dashboard` runs `gh attestation
  verify` (pinned to Threadline's own release workflow, the `main` branch
  and GitHub-hosted runners) before anything is published. If GitHub cannot
  confirm it, nothing is published and, when Node.js 22 or newer is
  installed, you are offered a local build instead. The SHA-256 check stays.

### Documentation

- The set-up guide, the README and the Claude set-up page no longer promise the
  morning summary e-mail without a condition: it needs a mailbox that can send
  it, such as Gmail with an app password.
- The guide and the README, rewritten around the one-line install and the
  single Supabase token, now say honestly how long it takes: about 30 to 40
  minutes of your own time if you already have GitHub, Supabase, Netlify and
  Claude Code, the first summary e-mail about ten minutes later, and 50 to 70
  minutes if you create the accounts too (the Claude route says the same).
  Claude Code is checked where it is first needed (part 6b), with the Windows
  order (install line first) said there; the first `uv sync` may download
  Python; the Claude set-up recipe opens the set-up page with `open`,
  `xdg-open` or `start` when it did not open itself, waits for the copy to
  finish filling before it makes the clone's backend, and says the terminal
  prints the `Stopped:` line too. Smaller fixes: the folder check works in
  PowerShell (`pwd`), "the two lines below" points at what it means, two broken
  line wraps, "Email address not authorized" is named as Supabase's message,
  and the GitHub part describes the git-name message, the missing mailbox for
  the e-mail, the Claude key check, LinkedIn's send to GitHub, the old `gh`
  stop, and the cloud route's offer to switch the GitHub run off.

- The install part of the guide now says what the one-line install changes: uv's
  installer adds uv to your PATH, `gh auth setup-git` lets git use your GitHub
  sign-in, and an empty git name and e-mail are filled in from your GitHub
  account. The installers' opening comments say the same. The guide also no
  longer says winget comes with every Windows 10 and 11 (it names App Installer
  as the way to get it), says the first run may download Python, and lists the
  new messages the installers can stop with.
- The `.env` privacy claim on Windows is now accurate: the file is private
  because it sits inside your user folder, not because of file permissions.

## [0.5.0] - 2026-10-08

This section also holds 0.3.0 (2026-10-03) and 0.4.0 (2026-10-04), which were
released without a heading of their own.

### Added

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
  `tracker setup refresh` switches it on (a fresh key in the function's
  settings and in Vault, the timer made sure of), `tracker setup schedule` and
  `tracker setup timezone` keep the daily time in the database in step with
  the workflow, and `tracker doctor` gains an **On-time morning start** line.
  Free on Supabase's free plan: pg_cron, pg_net and Vault are built in.
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

### Changed

- `tracker setup` stops at "Is the dashboard published already?" when the
  answer is no, instead of carrying on to steps that need the dashboard;
  running `uv run tracker setup` again carries on from there. A full run's
  stop line now names `uv run tracker setup` as the command to run again.
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
- The daily run starts at 07:00 Paris time instead of 07:00 UTC.
  `uv run tracker setup schedule` sets your own time and zone.

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
