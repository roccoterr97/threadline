# Setting it up: from nothing to your first morning summary

> **Would you rather not do this yourself?** Claude can run every command in
> this guide for you while you create the accounts and click where it says:
> see [`setup-with-claude.md`](setup-with-claude.md). It is one sentence to
> paste into the Claude app.

This guide takes you from nothing to the first summary e-mail, one small step at
a time. You do not need to know how to program. You paste one line into a
terminal, and a guided set-up does most of the work. Where only you can do
something, such as creating an account or clicking "Allow", this guide says
exactly what to click.

After every step there are two lines:

- **✅ Check:** what you should see if the step worked.
- **If not:** what to do if you see something else.

Do not skip a check. Each step builds on the one before it.

> **Websites change.** Button names below were right when this guide was
> written. Where a page may look slightly different, the guide says so. Look for
> a button with a similar name.

---

## Before you start

**What you need**

| What | Why | Cost |
|------|-----|------|
| A computer with **macOS, Linux or Windows** (10 or 11) | to run the set-up once. After that it can stay off | – |
| A paid Claude plan: **Pro, Max or Team** | runs the daily job on GitHub with your own subscription, with your computer off. The daily run uses part of your plan's usage limits, like any other use of Claude | your existing plan |
| A **GitHub** account | keeps your private copy of Threadline and runs it every day (GitHub Actions) | free (2,000 minutes a month for private copies at the time of writing; a month of runs uses about 150–300) |
| A **Supabase** account | the database that keeps your people and conversations | free plan |
| At least one mailbox: Gmail, Outlook.com/Hotmail, iCloud, Yahoo, Fastmail or any mailbox that offers IMAP | the mail Threadline reads, read-only. Gmail and the others also send you the summary (with only Outlook, see the Claude cloud route in part 8) | free (Fastmail: a paid plan above Basic) |
| *Optional:* a Microsoft personal account (Outlook.com, Hotmail, Live) | the calendar, which is read from Outlook only for now | free |
| *Optional:* a LinkedIn account | reads your LinkedIn messages too (only for members located in the EEA or Switzerland, see part 8) | free |

**What the installer needs on your computer.** The one-line install in part 1
adds the tools Threadline uses, Claude Code included. It needs a little help
depending on your computer:

- **Windows:** nothing extra on most computers. It installs Git and the GitHub
  tool with **winget**, Windows' own installer, which is part of the "App
  Installer" that current Windows 10 and Windows 11 come with. Some Windows 10
  editions (LTSC, Server, or an older build) do not have it. If the installer
  says winget is missing, get **App Installer** from the Microsoft Store
  (<https://aka.ms/getwinget>), or install Git from <https://git-scm.com/download/win>
  and the GitHub tool from <https://cli.github.com>, then paste the line again.
- **Mac:** Git must be installed. If it is not, the Mac offers to install it
  (the "command line developer tools") the first time. Homebrew is not needed:
  with Homebrew the installer uses it for the GitHub tool, and without it the
  installer downloads GitHub's own build for your Mac into the `.local/bin`
  folder in your home folder and checks it against GitHub's published checksums.
- **Linux:** Git and curl must be installed. The installer adds the GitHub tool
  from GitHub's own apt or dnf package source (the one `cli.github.com`
  describes), because the version your distribution offers is often too old,
  and may ask for your computer's password. Without apt, dnf or the right to
  install packages, it downloads GitHub's own build into `~/.local/bin` instead.

The GitHub tool must be version 2.68 or newer. The installer checks the one you
have and updates it if it is older.

**Create the two free accounts first.** Sign up at <https://github.com>, then
at <https://supabase.com> with **Continue with GitHub** (one click). The set-up
asks for Supabase in its very first step.

**Pages open in your default browser.** When the set-up opens a page
(GitHub, Supabase, Claude), it appears in your usual browser. If that browser
is signed in to a different account than the one you want to use, check the
account name at the top of the page before you click anything. If it is the
wrong one, copy the page's address into a window signed in to the right
account.

**The sign-in e-mail limit.** You will sign in to the dashboard with a link that
Supabase e-mails to you. Supabase's built-in e-mail only reaches the address
your Supabase account was registered with (or members of your Supabase
organisation), unless you set up your own sending service ("custom SMTP"). Part 3
explains what that means for you.

**Time.** About 20 minutes of your own time with GitHub and Supabase ready,
about 30 without. Part of it is waiting: a new Supabase project takes one to
three minutes to start, and the first download of Python can take a few more.
Making a Gmail app password takes longer if 2-Step Verification is not on yet.
The first summary e-mail follows about ten minutes after the set-up ends, but
only if you have a mailbox that can send it, for example Gmail with an app
password; with Outlook alone the dashboard fills and no e-mail comes (part 8c
has the Claude cloud route for that). You can stop at any point: the set-up
carries on where you left off.

**What it costs.** No other paid service is needed. GitHub, Supabase,
Google, Microsoft and LinkedIn are all used on their free plans; the only
exception would be a paid mailbox you choose yourself, such as Fastmail.
Free-plan limits change, so check the providers' pricing pages if in doubt.

**Your keys.** The settings the set-up saves are kept in a file called `.env`
in your Threadline folder. On a Mac or Linux only you can read it. On Windows
the folder is inside your user folder, which other ordinary accounts on the
computer cannot open by default (an administrator can); the file itself has no
extra lock. Some keys are never saved at
all: the set-up uses them and forgets them, and this guide says which. Never
paste a key into a chat, an e-mail or a document.

**Words used here.** A few words come up before they are explained:

- **IMAP** is the standard way a program reads a mailbox; **SMTP** is the
  standard way it sends mail. Your provider's help pages give a server name for
  each.
- An **app password** is a separate password made for one program only, which
  you can remove without changing your real password.
- **Secrets and variables** are the settings the run on GitHub reads. A secret
  is hidden in every log; a variable is a harmless setting shown in the open.
- **cron** is the line in the workflow file that says at what time the run
  starts each day.
- An **Edge Function** is a small helper that runs inside your Supabase
  project; the Refresh now button uses one. The **Management API** is the
  official way the set-up talks to Supabase on your behalf, after you let it
  in once with **Authorize** (part 2a).
- A **CRM** is customer-relationship software, which Threadline is not.
- The **EEA** is the European Economic Area: the EU plus Iceland, Liechtenstein
  and Norway.

---

## 1. Install Threadline (one line)

One line gets Threadline onto your computer. It installs **uv** (the tool that
runs Threadline), the **GitHub tool** and **Claude Code** if they are missing,
signs you in to GitHub, makes your own **private** copy of Threadline on GitHub
(called `threadline`), downloads it to a `threadline` folder in your home
folder, and starts the guided set-up. Claude Code comes from Anthropic's
official installer; the set-up uses it once, in part 6b, to make the key that
lets GitHub use your Claude plan.

**What the install changes on your computer.** Besides those tools and the
`threadline` folder, three things change, and the installer says so as it goes:

- **uv's own installer adds uv to your PATH.** That is the list of places your
  terminal looks for programs. On a Mac or Linux it adds a line to your shell's
  start-up file (such as `.zshrc` or `.profile`); on Windows it adds uv's folder
  to your user PATH. This is why a new terminal finds `uv`.
- **`gh auth setup-git` lets git use your GitHub sign-in.** It adds a line to
  your git settings so that git, when it talks to github.com, asks the GitHub
  tool for your sign-in instead of asking for a password.
- **Git's name and e-mail are filled in if they are empty.** Git records both
  with every change. If you never set them, the installer sets them from your
  GitHub account: your name, and GitHub's private address
  (`number+yourname@users.noreply.github.com`), so your real address is not
  shown. It tells you what it set, and it never changes values you already set.

1. Open a terminal.
   - **Mac:** press ⌘ + Space, type `Terminal`, press Enter.
   - **Windows:** open the Start menu, type `PowerShell`, press Enter.
   - **Linux:** open your terminal app.
2. Paste the line for your computer and press Enter.

   **Mac or Linux:**

   ```bash
   curl -LsSf https://raw.githubusercontent.com/roccoterr97/threadline/main/install.sh | sh
   ```

   **Windows (PowerShell):**

   ```powershell
   irm https://raw.githubusercontent.com/roccoterr97/threadline/main/install.ps1 | iex
   ```

3. If Windows asks whether to allow an installation, click **Yes**.
4. When it says `Signing you in to GitHub`, the terminal shows a one-time code.
   Press Enter, and a GitHub page opens in your browser. Sign in and type the
   code. Before you click **Authorize**, check the account name at the top of
   the GitHub page: if it is not the account you want Threadline on, click
   **Use a different account** and sign in with the right one. Then click
   **Authorize**. The page lists what it lets the GitHub tool do,
   including "workflow": that one is needed to save the daily-run file later.
   If the terminal asks whether to authenticate Git with your GitHub
   credentials, answer yes.
5. Wait. It makes your copy, downloads it and installs Threadline's parts. This
   takes a minute or two. The first time, installing the parts can also
   download Python itself, which can take a few minutes more; that is normal.

**✅ Check:** the terminal says `Starting the guided set-up`, then
`Step 1 of 11: Your Supabase project`. Carry on with part 2.

**If not:** every message that stops the installer says what to do, and
pasting the line again is safe: it skips what is already done and carries on.

- `Git is not installed yet` on a Mac: click **Install** in the window that
  offers the "command line developer tools", wait for it to finish, then paste
  the line again.
- `Could not download uv` or `Could not download the GitHub tool`: the internet
  connection dropped. Check it and paste the line again.
- Claude Code could not be installed: install it from Anthropic's page,
  <https://code.claude.com/docs/en/setup>, open a new terminal, and paste the
  line again.
- `The installation of Git did not finish (code …)` (or the GitHub tool) on
  Windows: Windows' question "Do you want to allow this app to make changes?"
  was closed or answered No, or the connection dropped. Paste the line again and
  click **Yes**. If it keeps failing, install that tool by hand from the address
  the message gives, then paste the line again.
- `Windows' installer (winget) is not on this computer`: get **App Installer**
  from the Microsoft Store (<https://aka.ms/getwinget>), then paste the line
  again.
- `The GitHub tool this computer uses is still version …`: the installer could
  not replace an old GitHub tool. Install the newest from <https://cli.github.com>,
  open a new terminal, and paste the line again.
- `… on GitHub is public`, `You are not the owner of …`, or `… is not a copy of
  Threadline`: your GitHub account already has a repository called `threadline`
  that is not your own private copy. Rename it on GitHub (Settings, then
  Repository name), or make it private if it is your copy, then paste the line
  again.
- `You are signed in to GitHub with the account that publishes Threadline`:
  that account holds Threadline itself, so it cannot have a copy of its own.
  Run `gh auth logout`, paste the line again, and sign in with another GitHub
  account.
- `An earlier Threadline set-up is already on this computer`: you set up an
  older version in `~/tracker`. Press Enter to carry on with it, or type `n` to
  make a fresh copy in `~/threadline`.
- `… was installed but cannot be found yet`: close the terminal, open a new
  one, and paste the line again.
- `Your copy on GitHub is not ready yet`: wait a minute and paste the line
  again.
- `… exists but is not a copy of Threadline`: you already have a different
  folder called `threadline` in your home folder. Rename it, then paste the line
  again.

**Stopping and carrying on.** You can stop the set-up at any time with
Ctrl + C. Everything it has saved stays saved. To carry on, paste the install
line again, or go to the `backend` folder as shown just below and type
`uv run tracker setup`.

**If a step stops.** The set-up shows only plain sentences. The technical
details go to a file called `setup.log` in the `backend` folder, and the set-up
names that file when it stops. If you ask someone for help, show them that
file. It never holds your keys.

**Where to type the commands.** Every `uv run tracker …` command in this guide
is typed in a terminal, inside the `backend` folder of your copy. In every new
terminal window, type this first (it works from any folder):

```bash
cd ~/threadline/backend
```

Then, for example, `uv run tracker setup` carries on with the set-up.

**Prefer a page to the terminal?** Add `--browser`:

```bash
uv run tracker setup --browser
```

A page called *Threadline set-up* opens in your browser and asks the same
questions, one at a time, with keys in hidden fields and a **Continue** button
where this guide says "press Enter". The page is served to your computer only
(its address starts with `http://127.0.0.1:`). The terminal still shows what is
asked, never what you answer. A **Stop for now** link at the bottom ends the
set-up cleanly; everything saved stays saved. `--browser` works with a single
step and with the extras too, for example
`uv run tracker setup database --browser`.

**✅ Check:** type `pwd` and press Enter. The folder it prints ends with
`backend`.

**If not:** `Failed to spawn: tracker` or `No such file or directory` means the
terminal is in another folder: type `cd ~/threadline/backend` and try again.
If you set Threadline up before the one-line install existed, your copy may be
in a folder called `tracker`: use that name instead of `threadline`.

**What the set-up does next.** It runs 11 steps in order, numbered on screen
(`Step 1 of 11`, `Step 2 of 11`, …). This guide follows the same order:

| Steps | Part of this guide |
|-------|--------------------|
| 1 to 3: Supabase, the encryption key, the database | [2](#2-supabase-one-click) |
| 4 to 6: your login, categories and time zone | [3](#3-your-login-categories-and-time-zone) |
| 7 and 8: your mailbox, and Outlook | [4](#4-your-mailbox-and-calendar) |
| 9: your dashboard | [5](#5-your-dashboard) |
| 10 and 11: the daily time, the Claude key and the first run | [6](#6-run-it-every-day-on-github-the-claude-key-and-the-first-run) |

To run one step again later, name it, for example
`uv run tracker setup database`. The optional extras (LinkedIn, the Refresh now
button and the Claude cloud route) come later, in part 8.

---

## 2. Supabase (one click)

Supabase is the database. You let the set-up into your Supabase account with
one click, and it does the rest: it creates the project (or reuses one of
yours), waits until it is up, reads its address and keys, builds the database,
and later switches off sign-ups.

### 2a. Sign in to Supabase, and your project (`tracker setup supabase`)

**What you do:**

1. The set-up asks `Create the project (or pick an existing one) for you?`.
   Press Enter for yes.
2. It asks how to let Threadline into your Supabase account. Press Enter for
   `1. Sign in to Supabase in your browser (easiest)`.
3. A Supabase page opens. Sign in if asked (**Continue with GitHub**), then
   click **Authorize**. The page may mention the "Supabase CLI": that is
   expected, Threadline signs in the same way.
4. The page shows a short verification code. Type it into the set-up and press
   Enter.
5. If you have several Supabase organisations, type the number of the one to
   use.
6. If you already have projects, it lists them (`1. name (running)`, or
   `(still being set up)`) and asks `Use one of them instead of creating a new
   project?`. Press Enter for yes when a project named `threadline` is running
   or starting (it is most likely the one an earlier try made), otherwise Enter
   means no and creates a new one. Type the answer you want if the default is
   not it.
7. Press Enter to accept the name `threadline`, then press Enter to accept the
   region it offers (the one nearest your time zone), or type another number.
8. Wait while Supabase starts the project. This takes one to three minutes.
   Do not press Ctrl-C meanwhile: the project is already being created, and
   stopping leaves it half set up. The set-up warns you of this.

Supabase now lists a key named `threadline-setup-…` under **Account → Access
Tokens**. That is the click you just gave. You may delete it once the set-up is
done (part 7).

The project's database password is made up for you and not kept: Threadline
never needs it. If you ever do, reset it in Supabase under **Project Settings →
Database**.

**✅ Check:** you see `The project is up.` (for a new project), then
`Supabase accepted the address and both keys.`

**If not:**

- `Supabase did not accept that code`: type the code the newest Supabase page
  shows. After three refused codes the set-up moves to pasting a token.
- `Signing in through the browser did not work this time`: the set-up moves
  to pasting a token, below.
- **I'd rather paste a token.** Type **2** at step 2, or follow on when the
  set-up moves here by itself. On Supabase's **Access Tokens** page
  (<https://supabase.com/dashboard/account/tokens>), click **Generate new
  token**, then the small link **Create legacy token** on the left (the newer,
  limited kind cannot read your project's secret key). Choose the shortest
  expiry, click **Generate token**, and paste the token (it starts with `sbp_`).
  Nothing appears while you paste. It is never saved.
- `Supabase did not accept the access token`: copy the token again, all of it,
  and paste it once more. The set-up lets you try three times.
- `Supabase says this access token has too little access`: you made the newer,
  limited kind of token. Make a new one with the **Create legacy token** link
  and paste that one.
- `your Supabase account has no organization yet`: open <https://supabase.com>,
  create an organisation (any name, free plan), then run
  `uv run tracker setup supabase`.
- If Supabase refuses to create the project, your free plan may already have as
  many active projects as it allows. Run `uv run tracker setup supabase` again
  and answer yes to use an existing project, or pause a project you no longer
  use in Supabase first.
- `'name' is paused`: the set-up no longer skips a paused project quietly. Open
  the project in Supabase and click **Restore project**, then run
  `uv run tracker setup supabase` again, or let it create a new project.
- `the project 'name' is still being set up after 5 minutes`: the project is
  already created, so do not create another. Run `uv run tracker setup supabase`
  again in a while and pick it from the list (Enter picks it).
- `a project may already have been created`: the request to create it was lost
  on the way. Run the step again and look at the list before creating anything.
- `The project does not answer yet` (a new project that is silent after about
  30 seconds): wait a minute and run `uv run tracker setup supabase` again.
- Running `uv run tracker setup supabase` again when `.env` already holds a
  complete project: it says `Your .env already points to the Supabase project
  <ref>.` and asks `Keep it?` (Enter keeps it) before it asks you to sign in.

**If you prefer** to create the project yourself, answer **n** at step 1. The
set-up then opens your Supabase projects and asks for the project address, the
publishable key and the secret key (under **Project Settings → API Keys**, tab
**Publishable and secret API keys**), checking each one as you paste it. The
later steps then ask you to sign in to Supabase once, for the database.

### 2b. The encryption key (`tracker setup encryption`)

**What the set-up does for you:** everything. It makes a key that locks your
Microsoft sign-in and your mailbox's app password inside the database, and
saves it without showing it.

**✅ Check:** you see `A new key was made and saved.` (or, on a second run,
`A usable key is already saved; it is kept.`)

**If not:** if it asks whether to replace an existing key, answer **no** unless
you know the old one is wrong. A new key means signing in to Microsoft again.

### 2c. The database (`tracker setup database`)

**What the set-up does for you:** it looks at your new database, lists the
structure files it needs, and applies them with the same sign-in, one at a
time, a second or two apart. This takes about half a minute. If Supabase
refuses a file, the set-up shows Supabase's reason in one line and tries that
file once more by itself.

Run on its own later (`uv run tracker setup database`), the step first asks
`Apply them automatically?`: press Enter, and sign in to Supabase as in 2a
(**Authorize**, then the code), or paste a legacy token.

**✅ Check:** the step starts with `To apply: 0001_schema, 0002_access_rules, …`,
naming every file still missing (all of them on a new project). Then you see
`Applied 0001_schema`, one line per file, and `The database structure is in
place.`

**If not:** if a file still fails, or Supabase refuses the sign-in when a file
is sent, the set-up switches to the manual route by itself: it opens the **SQL Editor**, puts each file on your clipboard in turn,
and waits. For each file: click **+** for a new query, paste, click **Run**,
wait for `Success. No rows returned`, and only then press Enter in the
terminal. Pressing Enter is not enough on its own: the set-up checks that the
file really ran, and if it did not, it says `The database does not show … yet`
and gives you the same file again. At the end it checks the database once
more. If it still lists a file as missing, run `uv run tracker setup database`
again.

---

## 3. Your login, categories and time zone

### 3a. Your dashboard login (`tracker setup login`)

The dashboard only lets in the one login recorded as its owner. Nobody else can
create a login, so nobody else can read your data.

**Which e-mail address to use.** You sign in to the dashboard with a link
Supabase e-mails to you. Supabase's built-in e-mail sends only **two messages
an hour**, and **only to the address your Supabase account was registered with
(or to members of your Supabase organisation)**. So use the same address you
signed up to Supabase with. (Another address needs your own e-mail sending
service, called "custom SMTP" in Supabase. This guide does not cover it.)

**What the set-up does for you:** it creates your login, records it as the only
owner, and switches off sign-ups in Supabase with the sign-in from part 2.

**What you do:** type the e-mail address you signed up to Supabase with, and
press Enter. If you signed in to Supabase with GitHub, it is the main e-mail
address of your GitHub account; Supabase shows it under **Account →
Preferences**.

**✅ Check:** you see `… can now sign in to the dashboard, and nobody else can
read it.` and then `Sign-ups are now switched off: nobody else can create a
login.` (or `Sign-ups are switched off` if they already were).

**If not:** if Supabase would not change the setting (also after a Supabase server
error or a timeout), the set-up opens the page
**Authentication → Sign In / Providers**. Switch off **Allow new users to sign
up**, click **Save**, and press Enter in the terminal. If the switch keeps
coming back on, reload the page, switch it off again and click **Save** before
pressing Enter.

### 3b. Your categories (`tracker setup categories`)

Threadline puts each person you talk to in a category, such as "Startup" or
"Investor". Here you choose those categories. This step is optional: skip it
and you keep the job-search categories, which you can change any time on the
dashboard's **Settings** page.

**What the set-up does for you:** it saves your categories to your database and
tells the AI helper about them.

**What you do:**

1. Answer **y** to "Choose your categories now?" (or **n** to skip; it won't
   ask again, and `uv run tracker setup categories` brings it back).
2. Type the number of the list closest to what you track, for example `3` for a
   job search or `5` for sales. Press Enter to accept the number it suggests.
3. It lists the suggested categories and asks "Use all of them?". Press Enter
   to keep them all. If you type `n`, it asks about each one: press Enter to
   keep it, or type `n` to drop it.
4. To add one of your own, answer **y**, then type its name ("Supplier"), a
   name for a group (press Enter to accept "Suppliers"), who belongs there in
   one sentence ("Companies that sell to us") and a colour (press Enter to
   accept the one offered). The sentence matters: the AI helper reads it to
   decide who goes where. Answer **n** when you have no more to add.
5. Look at the list it shows, then press Enter to save it.

**✅ Check:** you should now see `Saved … categories, 'Not known' included.`
Once your dashboard is ready (part 5), its **Settings** page shows the same
categories.

**If not:** "That did not work" means a name was empty, too long, already in
your list, or the colour was not one of those offered: type it again. If you
answered **n** by mistake, run `uv run tracker setup categories` again.

### 3c. Your time zone (`tracker setup timezone`)

**What the set-up does for you:** it reads the time zone your computer uses and
offers it, such as `Your time zone [Europe/Paris]:`. If it cannot tell (a Windows
zone name it does not know, for example), it says "I could not tell your time
zone", offers nothing and waits for you to type it. Your time zone decides what
"today" is for due dates and the summary, and the daily run's time (part 6) is
read in it. It is saved as `OWNER_TIME_ZONE` and later sent to GitHub with your
other settings. When the zone differs from the one in the daily run's workflow
file (`.github/workflows/threadline-run.yml`), it writes the new zone there
too, keeping the time, shows the line it changed and offers to send it to
your copy on GitHub, as in part 6a.

**What you do:**

1. Press Enter (or type `y`) to keep the zone offered, or type yours in the
   same form (`America/New_York`, `Asia/Tokyo`, `UTC`). When no zone is
   offered you must type one; an empty answer is asked again. Capital letters do not matter:
   `europe/rome` is accepted and saved as `Europe/Rome`.
2. It then asks for your name as people write it (such as `Sam Rivera`). This
   is optional: it helps only when your e-mail address does not spell your name
   (`jd123@…`). Leave it empty and press Enter to skip it.

**✅ Check:** you see `Saved OWNER_TIME_ZONE=…` with your zone.

**If not:** "that is not a time-zone name" means it was typed in another form:
use the region and the city with a slash, such as `Europe/Rome`. To change it
later, run `uv run tracker setup timezone`.

---

## 4. Your mailbox and calendar

Threadline needs **at least one mailbox**: Gmail, Outlook.com/Hotmail, iCloud,
Yahoo, Fastmail, or any other mailbox that offers IMAP. It only ever reads:
nothing is sent, moved, deleted, or even marked as read.

**The calendar is read from Outlook only, for now.** With Gmail alone,
Threadline reads your e-mail, including interview invitations that arrive by
mail, but not your Google Calendar.

### 4a. Choose your mailbox (`tracker setup mailbox`)

The set-up asks: *Which mailbox should Threadline read? gmail, outlook, icloud,
yahoo, fastmail or other*. Type one word and press Enter.

- **outlook** (also for Hotmail and Live): go on to
  [4c](#4c-outlook-mailbox-and-calendar-tracker-setup-microsoft). Good to know
  now rather than in part 6: with Outlook alone, the run on GitHub cannot
  e-mail you the morning summary, because Microsoft allows no app password for
  sending. Connect a Gmail or other mailbox as well (run
  `uv run tracker setup mailbox` again later), or use the
  [Claude cloud route](#8c-the-claude-cloud-route-tracker-setup-cloud).
- **anything else**: follow 4b below for your provider.

**✅ Check:** the set-up either asks for your address (4b) or says the Microsoft
step signs you in (4c).

**If not:** if it says "please answer gmail, outlook, …", type one of those
words exactly.

### 4b. Gmail (or another mailbox)

Gmail, iCloud, Yahoo and Fastmail do not let other programs use your normal
password. Instead you make an **app password**: a separate password just for
Threadline, which you can remove at any time. Your normal password is never
given to Threadline.

**What the set-up does for you:** it asks for your address, explains app
passwords, opens your provider's page, and waits for you to paste the new
password (nothing is shown while you paste). Then it **checks it live**: it
signs in, opens your inbox read-only, counts the messages of the last 30 days
and looks for your Sent folder. Only then does it store the password,
encrypted, in your database, **never in `.env`**, and offer to add the address
to your own addresses.

**✅ Check (for every provider):** the terminal shows
`Connected. Your inbox has … messages from the last 30 days.`, then
`Your own replies are read from the folder '…'.` and
`Saved the app password, encrypted, in your database - it is not in .env.`

**If not:** "refused the app password" means the password was copied wrongly,
belongs to another address, or the account does not allow app passwords: see
your provider below. The set-up lets you paste again twice. "No Sent folder was
found" still works, but your own replies will not be read: tell the project
which folder your mail program saves sent mail in.

#### Gmail

1. **Turn on 2-Step Verification.** Open <https://myaccount.google.com/security>,
   find **2-Step Verification** and follow Google's steps (you need your phone).
   The page may look slightly different.

   **✅ Check:** the Security page shows 2-Step Verification as **on**.

   **If not:** finish Google's steps; app passwords appear only once it is on.

2. **Make the app password.** Type `gmail` and your Gmail address in the
   terminal. The set-up opens <https://myaccount.google.com/apppasswords>. Sign
   in if asked, type a name such as `Threadline`, and create it. The page may
   look slightly different.

   **✅ Check:** Google shows a 16-character password. Copy it now: Google shows
   it only once.

   **If not:** if Google says the setting is not available, one of these is
   true: 2-Step Verification is off; you sign in only with security keys;
   Advanced Protection is on; or it is a work or school account whose
   administrator switched app passwords (or IMAP) off. Only the administrator
   can change the last one: use Outlook instead, or ask them.

3. **Paste it in the terminal** and press Enter. Spaces do not matter.

   **✅ Check:** the lines of the general check above, with the folder
   `[Gmail]/Sent Mail` (or its name in your language).

   **If not:** make a new app password and paste that one.

Good to know: IMAP is always on for personal Gmail accounts, so there is no
setting to switch on. **Changing your Google password removes every app
password**: see "Renew a mailbox app password" in
[`operations.md`](operations.md).

#### iCloud Mail

1. **Two-factor authentication** must be on for your Apple Account (it usually
   is).

   **✅ Check:** at <https://account.apple.com>, **Sign-In and Security** lists
   **App-Specific Passwords**.

   **If not:** turn on two-factor authentication on your iPhone or Mac first.

2. **Make the password.** Type `icloud` and your iCloud address. The set-up
   opens <https://account.apple.com>. Sign in, open **Sign-In and Security** →
   **App-Specific Passwords** → **Generate an app-specific password**, name it
   `Threadline`, and follow the steps. The page may look slightly different.

   **✅ Check:** Apple shows the new password.

   **If not:** check you are signed in with the Apple Account that owns the
   mailbox.

3. **Paste it in the terminal.**

   **✅ Check:** the general check above.

   **If not:** Apple's help says the sign-in name is usually the part of your
   address **before the @**. Run `uv run tracker setup mailbox` again, answer
   `other`, server `imap.mail.me.com`, port `993`, and type only the part
   before the @ as the sign-in name. When it asks for the sending server, type
   `smtp.mail.me.com` and port `587`.

Good to know: changing or resetting your Apple Account password removes every
app-specific password.

#### Yahoo Mail

1. **Make the app password.** Type `yahoo` and your Yahoo address. The set-up
   opens <https://login.yahoo.com/account/security>. Under **External
   connections**, click **Create app password**, type `Threadline`, then
   **Generate password**. The page may look slightly different.

   **✅ Check:** Yahoo shows a new password.

   **If not:** Yahoo sometimes refuses from a browser it does not know yet. Use
   a browser you usually sign in to Yahoo with, not a private window, and try
   again later.

2. **Paste it in the terminal**, then click **Done** on Yahoo's page.

   **✅ Check:** the general check above.

   **If not:** make a new app password and paste that one.

Good to know: Yahoo keeps app passwords when you change your password; remove
old ones yourself on the same page.

#### Fastmail

IMAP needs a paid Fastmail plan above Basic.

1. **Make the app password.** Type `fastmail` and your Fastmail address. The
   set-up opens Fastmail's help page about app passwords. In Fastmail, open
   **Settings** → **Privacy & Security** → **Connected apps & API tokens** →
   **Manage app passwords and access** → **New app password**. Choose a name,
   set the access to **Mail (IMAP/POP/SMTP)**, then **Generate password**. The
   page may look slightly different.

   **✅ Check:** Fastmail shows a 16-character password.

   **If not:** if there is no such setting, your plan does not include IMAP.

2. **Paste it in the terminal.** Wait for the check to pass before clicking
   **Done** on Fastmail's page.

   **✅ Check:** the general check above.

   **If not:** make a new app password with Mail access and paste that one.

#### Any other mailbox

1. In your provider's help pages, find its **IMAP server** name (such as
   `imap.example.com`) and port (almost always `993`), and how to make an
   **app password**.

   **✅ Check:** you have a server name and an app password.

   **If not:** if your provider offers no app passwords, it may accept your
   normal password; Threadline stores it encrypted the same way, but an app
   password is safer because you can remove it on its own.

2. Type `other`, then the server, the port (press Enter for 993), the name
   you sign in with (usually your address), and paste the password.

3. Once your mailbox is saved, the set-up asks for the **sending server**
   (SMTP), which it needs to e-mail you the morning summary from this mailbox
   (the usual way; it skips this when you chose another way to send the
   summary). Your provider's help pages list it next to the IMAP server. It
   suggests a name (for `imap.example.com` it offers `smtp.example.com`): press
   Enter to accept it, or type the right one. Then type the port, **465** or
   **587** (press Enter for 465). The set-up signs in to that server once with
   the same app password, to catch a wrong server now rather than every
   morning. It sends nothing.

   **✅ Check:** after the general check above, you see
   `Signed in to the sending server. Nothing was sent.`

   **If not:** "did not answer" means the server name or port is wrong, or the
   provider does not offer it over TLS on that port. The set-up asks
   `Try another server or port?`: press Enter to try again, or type `n` to
   carry on without it for now. After three tries it carries on by itself.
   Either way your mailbox stays connected and is read every morning; only the
   morning summary cannot be e-mailed yet. Check the name and port in your
   provider's help pages, then run `uv run tracker setup mailbox` again: it
   asks for the app password once more (make a new one if you no longer have
   it) and then for the sending server. Then run `uv run tracker setup github`,
   so the run on GitHub is told the sending server too. A sending server saved
   for a different mailbox is removed at this point, so the summary is never
   sent through the wrong one. Later, `uv run tracker doctor` shows a **Summary
   e-mail** line for the sending server.

### 4c. Outlook mailbox and calendar (`tracker setup microsoft`)

If you chose another mailbox in 4a, this step asks first whether to connect
Outlook as well. Answer **no** to skip it: the set-up remembers that and won't
ask again (it says `Skipped earlier`). You can add it later with
`uv run tracker setup microsoft`.

**What the set-up does for you:** it asks Microsoft for a short one-time code,
opens Microsoft's page, waits while you sign in, stores the resulting key
encrypted in your database, and reads your calendar once to show who signed in.
From then on the key renews itself every day.

**What you do:**

1. Type the code shown in the terminal on the Microsoft page that opens.
2. Sign in with your Outlook.com or Hotmail account.
3. Microsoft lists the permissions: **read your mail**, **read your calendars**,
   and **keep access**. All are read-only. Click **Accept** (or **Yes**).
4. Back in the terminal, answer **yes** when it offers to save the signed-in
   address as one of your own.

**✅ Check:** you see `Signed in as you@example.com.` with your own address.

**If not:** if Microsoft says the code expired, run
`uv run tracker setup microsoft` again: you have fifteen minutes to type it. If
Microsoft refuses the application itself, see "Your own Microsoft application"
below.

#### Your own Microsoft application (optional)

By default the sign-in goes through the public application of an open-source
project (ms-365-mcp-server). That is enough for almost everybody. If you would
rather use your own:

- Since June 2024 Microsoft only lets you register an application inside a
  directory, and **a personal Microsoft account alone cannot do that**. You need
  a free Azure account, which comes with a directory.
- In the Microsoft Entra admin centre: **App registrations → New
  registration**; account type **Personal Microsoft accounts only**; then
  **Authentication → Allow public client flows: Yes → Save**; then add the
  delegated Microsoft Graph permissions `Mail.Read`, `Calendars.Read` and
  `offline_access`. (The exact clicks were not checked and the pages may look
  slightly different.)
- Put the application's ID in `.env` as `MICROSOFT_CLIENT_ID=…` and run
  `uv run tracker setup microsoft` again.

**✅ Check:** `Signed in as …` appears with your own address.

**If not:** remove the `MICROSOFT_CLIENT_ID` line from `.env` to go back to the
default, and run `uv run tracker setup microsoft` again.

---

## 5. Your dashboard

The dashboard is the web page that shows your people and conversations. You
use the **shared dashboard** at <https://app.threadlineapp.com>: nothing to
publish, no extra account. The page is the same for everyone. Your data stays
in your own Supabase database, and only your e-mail address can sign in.

**What the set-up does for you:** it points Supabase's sign-in link at the
shared dashboard and gives you your **personal link**. That link opens your own
dashboard. It carries your database's public address, nothing secret. The
set-up saves it, so every morning summary e-mail carries it too.

**What you do:**

1. When the set-up offers the shared dashboard, press Enter (yes).
2. Write down the personal link it shows. It starts with
   `https://app.threadlineapp.com`.

**✅ Check:** on your phone, open your personal link, type your e-mail, and
click the link in the e-mail Supabase sends. The dashboard opens (it is empty
until the first run).

**If not:** "This address cannot sign in" on the dashboard means you typed
another address than your dashboard login: use the one you typed in part 3a,
usually your Supabase address. "Too many links were asked for" means waiting as
long as it says. Supabase's own message "Email address not authorized" means
the address is not the one of your Supabase account (see part 3a). A link that
opens `localhost` means the sign-in link was not connected: run
`uv run tracker setup dashboard` again. Running it again keeps the sign-in
addresses you already have in Supabase and adds the new one; it tells you which
it did.

**On a new device.** Open your personal link once (it is in every morning
e-mail), then sign in with the link Supabase e-mails you.

**Put it on your home screen.** Open your personal link in your phone's
browser. On an iPhone, tap **Share → Add to Home Screen**. On Android, tap
**⋮ → Add to Home screen**. It then opens like an app.

Would you rather have your own copy of the dashboard, at your own address? See
[8d](#8d-your-own-dashboard-on-netlify-tracker-setup-dashboard). It is
optional.

---

## 6. Run it every day on GitHub: the Claude key and the first run

Every morning GitHub starts Threadline on your private copy, runs the daily
job with **your own Claude subscription**, and e-mails you the summary from
your own mailbox, with your computer off. At the time of writing, GitHub's
free plan includes 2,000 minutes a month for private repositories; one run
takes about five to ten minutes, so a month of mornings uses roughly 150 to 300.

**Which mailbox sends the summary.** Threadline sends it from the Gmail,
iCloud, Yahoo, Fastmail or other mailbox you connected in part 4, with the same
app password (no new password to make). If you connected **only Outlook**, it
cannot: Microsoft requires its own sign-in method (OAuth2) for Outlook.com,
Hotmail and Live mail programs, and turned off plain passwords and app
passwords for them in September 2024. You have two choices: connect a Gmail or
other mailbox as well in part 4 (Threadline can read both), or use the
[Claude cloud route](#8c-the-claude-cloud-route-tracker-setup-cloud), which
sends through Claude's Gmail connector.

The GitHub step checks this before it does anything. If no mailbox with an app
password is connected, it says so plainly and offers to run the mailbox step
right then (answer yes and connect Gmail, or another mailbox, as in part 4).
If you still have none, the first run is **not** offered by default and nothing
promises you an e-mail: the dashboard is updated every morning, but no summary
e-mail arrives until you connect a mailbox (`uv run tracker setup mailbox`, then
`uv run tracker setup github`) or switch to the cloud route.

### 6a. The daily time (`tracker setup schedule`)

**What the set-up does for you:** it asks what time the run should start, reads
it in the time zone you gave in part 3c, writes both into the workflow file
`.github/workflows/threadline-run.yml`, and shows you the two lines it changed.
GitHub follows your summer and winter time by itself.

**What you do:**

1. Type the time on the 24-hour clock, such as `07:07`, or press Enter to keep
   the one offered (07:00 unless you chose another before). GitHub's own timer
   is busiest on the hour and often starts a run late, sometimes by hours; the
   Refresh now extra ([8b](#8b-refresh-now-tracker-setup-refresh)) makes your
   Supabase project start it on time instead.
2. When it asks `Send the new time to your copy on GitHub now?`, press Enter
   (yes). GitHub only uses the new time once the change is uploaded.

**✅ Check:** you see `Committed and pushed. GitHub will use the new time from
now on.`

**If not:** if you answered **n**, run the `git` lines the set-up printed
(they work from any folder of the project), or run
`uv run tracker setup schedule` again and answer **y**: the set-up notices that
GitHub does not have your time yet and offers the upload again, even though the
file itself needs no change. If the set-up stops with `Stopped: git does not
know who you are, so it cannot save the change`, git has no name to put on the
change yet. Run these two lines once, with your own name and address:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Then run `uv run tracker setup` again. Any other reason git gives is shown in
the same line, after `git said:`.

To use a different time zone later, run `uv run tracker setup timezone`: it
moves the workflow's zone too, keeping the time.

### 6b. The Claude key and your settings on GitHub (`tracker setup github`)

The run on GitHub cannot read the `.env` file on your computer, so your
settings go into your copy's **secrets** (hidden in every log) and
**variables** (the harmless ones, such as your time zone). GitHub also needs a
key that lets it use your Claude subscription. The set-up makes that key for
you with Claude Code, which the install line added.

**What you do:**

1. On a Mac or Linux, it asks `Make the Claude key now? A Claude page opens in
   your browser: click Authorize`. Press Enter for yes.
2. A Claude page opens. Sign in if asked, with the account of your Claude plan,
   and click **Authorize**. The key goes straight to GitHub: you never see or
   copy it. It lasts one year. The set-up waits up to 5 minutes for the click.
3. When it asks `Save … secrets and … variables in … with the GitHub CLI now?`,
   press Enter for yes.

Running this step again later, it asks `GitHub already has a Claude key. Make
a new one now?`. Enter keeps the key GitHub has; type `y` for a new one, for
example once a year when the key runs out.

**If the set-up asks you to paste the key** (always on Windows, and on a Mac or
Linux when it says `The key could not be made here`):

1. Open a **second** terminal window and type:

   ```bash
   claude setup-token
   ```

2. Sign in in the browser that opens, then go back to that second window: it
   prints a long key that starts with `sk-ant-oat`. The key is split over two
   lines. Copy it from the first letter to the last, including the second line.
3. Paste it into the set-up in the first window (nothing shows while you
   paste) and press Enter. If the key looks cut short, the set-up asks you to
   paste its second line, or the whole key again. Pressing Enter on an empty
   line keeps the key GitHub already has, if any (useful when you run the step
   again). If GitHub has no key, the set-up does not start the first run,
   because the run would do nothing: it tells you to run
   `uv run tracker setup github` again.

The key is never saved on your computer, not even in `.env`. Anyone with this
key can use your Claude subscription, so never paste it anywhere else.

**What the set-up does for you:** it saves every secret and variable on your
copy and names each one as it goes, never its value. The **secrets** include
the Claude key, your Supabase keys, the encryption key, your own addresses
(`OWNER_EMAIL_ADDRESSES`), and, when you have set them, `IMAP_USERNAME`,
`DASHBOARD_BASE_URL` and `OWNER_DISPLAY_NAME`. The **variables** are the
harmless settings, such as `OWNER_TIME_ZONE`, `MAIL_SOURCES` and
`IMAP_PROVIDER`.

If you emptied a setting on your computer (for example you removed
`OWNER_DISPLAY_NAME` from `.env`) and GitHub still holds it, the set-up lists
each one by name and asks once whether to delete them on GitHub, so the daily
run stops using the old values. Press Enter to delete them, or type `n` to keep
them.

**✅ Check:** the list names every secret and variable it set, ending with
`Done. GitHub has everything it needs to run Threadline on your copy.`

**If not:** if the Claude page did not open, or you closed it, run
`uv run tracker setup github` again. `That key is cut short`, `That is an API
key` or `That is not the key` means a pasted key was not the whole key from
`claude setup-token`. Go back to the second window and copy it again, from
`sk-ant-oat` to the last letter of the second line, and paste it when the
set-up asks again.

If the set-up stopped with `there is no private copy on GitHub
yet`, this folder is not linked to your own private copy. Paste the install
line from part 1 again: it makes the copy and downloads it.

If it stopped with `your GitHub CLI is too old`, the `gh` on your computer
is from before 2.68 and lacks commands Threadline uses. Install the newest from
<https://cli.github.com> (or run the install line from part 1 again), then run
`uv run tracker setup github`. The set-up says this at the first use of `gh`,
not at the end.

### 6c. The first run starts by itself

Right after saving, and once it has seen that GitHub holds your Claude key, the
set-up asks `Start the first daily run on GitHub now?`. Press Enter for yes. It
makes sure GitHub Actions and the workflow are switched on in your copy, then
starts the run. (When no summary e-mail can be sent from GitHub, the question
says so and Enter means no. You may still answer yes to fill the dashboard.)

The set-up then watches the run for up to two minutes, to catch a problem
early (`Watching it for up to 2 minutes, to catch a problem early...`).

**✅ Check:** you see `The first run has started.`, then
`It is running; the summary e-mail comes in about 10 minutes.` and the address
of the run's page. (If the run already finished, it says `The first run has
finished.` instead.)

**If not:**

- `The first run stopped with a problem.`, followed by the reason: do what that
  line says. Most often it is `Claude did not accept the key saved on GitHub`.
  Run `uv run tracker setup github` again: it makes a new key the same way (if
  it asks you to paste one, paste both lines), and answer yes to start a new
  first run.
- If GitHub refused to start the run, the set-up says so in one line and names
  the page where you start the run yourself:

  1. Open that page (**Actions → Threadline run** in your copy on GitHub). If
     it shows **Enable workflow**, click it.
  2. Click **Run workflow**, keep **mode: daily**, and click the green **Run
     workflow** button.

The same steps apply if you set Threadline up without the installer and the
set-up could not use the GitHub tool: it then lists the setting names to add on
**Settings → Secrets and variables → Actions**, puts each value on your
clipboard in turn, and ends with the same two steps.

### 6d. See the run, and the e-mail

On the run's page, a new run appears with a yellow dot and, after about five to
ten minutes, has a green tick. Open the finished run and click **Threadline**,
then **Run the recipe with Claude**: the log ends with Claude's short report of
the run, in plain English. It never contains the text of your messages.

**✅ Check:** within about ten minutes of the start, the summary e-mail is in
your inbox, sent from your own mailbox, and the dashboard's **Daily runs** page
shows the run as **Worked** or **Partly worked**.

**If not:**

- *Green tick after a few seconds, nothing sent:* a required secret is
  missing. Open the run; a note at the top names the missing secrets. Run
  `uv run tracker setup github` again.
- *Red cross:* open the run. When Claude stopped with an error, a line titled
  **Why Claude stopped** at the top of the run's page says why, such as a
  refused key, the plan's usage limit, or Claude being busy, and what to do.
  For a refused key, run `uv run tracker setup github` again: it makes a new
  key. Without that line, click **Threadline** and open the step with the red
  cross.
- *Green tick but no e-mail:* a green tick only means the job ran, not that
  every part worked. Read Claude's report at the end of the log, then run
  `uv run tracker doctor` on your computer: its **Summary e-mail** line checks
  that your mailbox accepts the app password for sending, without sending
  anything.
- *A run stopped half-way (cancelled, or GitHub stopped it):* nothing to clean
  up. The dashboard's **Daily runs** page shows it as **Running** for a while;
  when the next run starts (at least three hours later), it is closed as
  **Did not work**, with the step where it stopped marked "The run stopped
  here and never finished", and the next morning summary mentions it once.

From now on the run starts by itself every day at the time you chose, as
GitHub's timer allows; with Refresh now switched on (part 8b), exactly on time.

---

## 7. The final check

The set-up ends by saying `Set-up done.`, then your dashboard's personal link
and the e-mail address that can sign in to it (`Sign in there with …`: write
both down). It then says how the first run was left (and, when it was started and an
e-mail can be sent, when the first summary e-mail will arrive), the daily time,
and how to add the extras. Then it checks every connection once and prints one
line for each. The technical details of the whole set-up are in
`backend/setup.log`, if anyone helping you needs them.

You can run the same check yourself at any time:

```bash
uv run tracker doctor
```

**✅ Check:** the last line says `Everything Threadline needs is working.` Lines
start with `ok`, or with `skipped` or `warning` for the optional parts. Until
you add the extras (part 8), these are expected:

- `skipped  LinkedIn …: LinkedIn is not connected (optional)`
- `warning  Refresh now: not switched on yet (optional)`
- `warning  On-time morning start: not switched on (optional): GitHub alone
  starts the daily run, often late`

**If not:** fix the lines marked `PROBLEM` from top to bottom. Each one ends
with the command that repairs it, usually `uv run tracker setup <step>`.

You are done. You can now delete the Supabase key named `threadline-setup-…`
(or the token you pasted) under **Account → Access Tokens** on Supabase. From
now on, [`operations.md`](operations.md) is the page to
keep: what happens every morning, and what to do when the summary asks for
something.

---

## 8. Extras (optional, later)

Three extras can be added at any time. None of them is needed for the morning
summary, though Refresh now also makes it arrive on time. To go through all
three in order, each one skippable:

```bash
uv run tracker setup extras
```

It shows `Step 1 of 3` (LinkedIn), `Step 2 of 3` (Refresh now) and
`Step 3 of 3` (the Claude cloud route). To do one alone, name it:
`uv run tracker setup linkedin`, `uv run tracker setup refresh` or
`uv run tracker setup cloud`.

One more choice is in [8d](#8d-your-own-dashboard-on-netlify-tracker-setup-dashboard):
your own copy of the dashboard on Netlify, for people who would rather not use
the shared one.

### 8a. LinkedIn (`tracker setup linkedin`)

LinkedIn offers no ready-made sign-in button for this, so the first time you
make a small "developer application" on LinkedIn's pages and connect it to
Threadline. After that, a new key is one command and one click. Before you
decide, here is what to expect:

- **It is optional.** Everything else works without LinkedIn.
- **It depends on where your LinkedIn profile is located.** LinkedIn offers
  this only to members whose profile is located in the European Economic Area
  or Switzerland. It is the location on your profile that counts, not your
  citizenship. If you live elsewhere, skip LinkedIn.
- **LinkedIn messages appear a day or two late.** LinkedIn's copy of your
  messages runs one to two days behind (measured on 24 September 2026), so a
  message you receive on LinkedIn today shows up in Threadline tomorrow or the
  day after. Nothing is lost; it only arrives later.
- **The first time takes about ten minutes.** When the key expires, you run
  one command and click **Allow** once (see
  [When the key expires](#when-the-key-expires) below).

<!-- The one-to-two-day delay is recorded beside LINKEDIN_OVERLAP_DAYS in
     backend/src/tracker/shared/constants/collection.py. -->

**What the set-up does for you:** it takes you through three stages in order
and opens the right LinkedIn page for each one. In the last stage it puts the
address you need on your clipboard, opens LinkedIn's **Allow** page, catches
LinkedIn's answer on your own computer, and reads from LinkedIn the day the
key expires, so you never copy the key or type a date. It makes one small call
to LinkedIn with the new key and saves it only if LinkedIn accepts it. The
application's Client Secret is kept encrypted in your Supabase database, never
in a plain file.

**What you do:** answer **yes** to "Connect LinkedIn now?" (or press Enter to
skip LinkedIn), then follow the stages below as the pages open.

#### Stage 1 of 3: create the developer application

The set-up opens LinkedIn's "Create an app" form,
<https://www.linkedin.com/developers/apps/new>. Sign in to LinkedIn if it asks.

1. **App name:** anything, for example `Threadline`.
2. **LinkedIn Page:** type `Member Data Portability` and choose the page
   LinkedIn suggests for this product, **Member Data Portability (Member)
   Default Company**. Do **not** create a new page.
3. If the form asks for an **App logo**, upload any small square picture (a
   screenshot works).
4. Tick the terms and click **Create app**.
5. Go back to the terminal and press Enter.

**✅ Check:** your new application's page opens with tabs such as **Settings**,
**Auth** and **Products**.

**If not:** if LinkedIn asks you to verify the page, make sure you picked the
default company named above. If you already created the application on an
earlier try, do not make a second one: open
<https://www.linkedin.com/developers/apps> and click it in the list instead.

#### Stage 2 of 3: add the Member Data Portability product

Stay on your application's page, the one stage 1 ended on.

1. Open its **Products** tab.
2. Find **Member Data Portability API (Member)** and click **Request access**.
3. Read and accept the terms.
4. In the terminal, answer **yes** to "Did LinkedIn let you request access?"
   (or press Enter).

**✅ Check:** the product is listed under the products your application has
(the page may look slightly different).

**If not:** if LinkedIn says the product is not available to you, your profile
is most likely not located in the EEA or Switzerland. Answer **no**. The set-up
says `Skipped: …`, saves nothing, and Threadline carries on without LinkedIn.

<a id="stage-3-of-3-make-the-key"></a>

#### Stage 3 of 3: connect the application to Threadline

Stay on your application's page. You do this stage once; later keys need only
the **Allow** click in step 6.

1. Open its **Auth** tab.
2. Under **OAuth 2.0 settings**, click the pencil next to **Authorized
   redirect URLs for your app**, then **+ Add redirect URL**.
3. Paste this address, exactly as it is, and click **Update**. The set-up has
   already put it on your clipboard:

   ```text
   http://localhost:8746/linkedin
   ```

4. Go back to the terminal and press Enter.
5. At the top of the same **Auth** tab, under **Application credentials**:
   copy the **Client ID**, paste it in the terminal and press Enter. Then click
   the eye icon next to **Primary Client Secret**, copy it, paste it in the
   terminal and press Enter. Nothing appears as you paste the secret; that is on
   purpose.
6. LinkedIn's page opens and asks to let your application read your data.
   Sign in if asked and click **Allow**. The tab then says
   `Threadline has LinkedIn's answer. You can close this tab and go back to the set-up.`
7. The first time only, paste your profile address
   (`https://www.linkedin.com/in/…`) in the terminal.

**✅ Check:** you see `LinkedIn made a new key. It works until …` with a date,
then `LinkedIn accepted the key.`, then `Saved LINKEDIN_CLIENT_ID in .env.`,
`Saved the Client Secret, encrypted, in your Supabase database.` and the same
`Saved …` line for `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_TOKEN_EXPIRES_ON` and
`OWNER_LINKEDIN_PROFILE_URL`.

**If not:** each problem has its own line. After it, answer **y** to
`Try again?` and the set-up opens LinkedIn's page again (up to three tries).

- LinkedIn's own page shows **"The redirect_uri does not match the registered
  value"**: the address in step 3 is not exactly the one above. Fix it on the
  **Auth** tab. After two minutes the terminal asks
  `No answer from LinkedIn yet. Keep waiting?`: answer **n**, then **y** to
  `Try again?`. When it asks for the Client ID and Client Secret again, press
  Enter to keep what you typed.
- LinkedIn's own page shows **"invalid client_id"**: the Client ID was not
  copied whole. Do as in the line above and type the Client ID again.
- `LinkedIn did not accept the Client ID or the Client Secret`: copy both
  again from the **Auth** tab when the set-up asks.
- `LinkedIn has not given your application the … product yet`: check the
  **Products** tab (stage 2). Wait a few minutes after requesting it.
- `LinkedIn says the sign-in was cancelled`: you clicked **Cancel** or did not
  sign in. Try again and click **Allow**.
- `Another program on this computer is using port 8746`: another set-up is
  probably still open in a different terminal window. Close it and try again.

If it still does not work, answer **n** to `Try again?`: the set-up offers to
make the key by hand instead (next section).

<a id="the-expiry-date-and-your-profile-address"></a>

#### Making the key by hand

This is the older way, and it always stays available. The set-up offers it
when the one-click way did not work (`Make the key by hand on LinkedIn's token
page instead?`), and on a renewal when you answer **n** to `Set that up now?`.

1. The set-up opens LinkedIn's token page,
   <https://www.linkedin.com/developers/tools/oauth/token-generator> (in
   LinkedIn's own menu: **Docs and tools → OAuth Token Tools → Create token**).
2. Pick your application.
3. Tick the permission (scope) whose name starts with **`r_dma_portability`**.
   LinkedIn's own pages name it slightly differently in different places.
4. Click **Request access token**, sign in if asked, and click **Allow**.
5. Copy the token LinkedIn shows. It is shown only once. Paste it in the
   terminal and press Enter. Nothing appears as you paste; that is on purpose.
6. If you typed the Client ID and Client Secret in stage 3, the set-up asks
   LinkedIn when the key expires and shows `LinkedIn says this key works
   until …`. Otherwise it asks you for that day: open **Docs and tools → OAuth
   Token Tools → Token Inspector** on the same LinkedIn page, pick your
   application, paste the token, click **Inspect** and type the expiry date it
   shows. `2027-09-24`, `24 Sep 2027`, `24 September 2027` and `Sep 24, 2027`
   all work. A date with only numbers and slashes, such as `03/04/2027`, is
   refused, because it could mean two different days.

**✅ Check:** you see `LinkedIn accepted the key.`, then
`Saved LINKEDIN_ACCESS_TOKEN in .env.` and the same line for
`LINKEDIN_TOKEN_EXPIRES_ON`.

**If not:** if **Request access token** is greyed out, the product from stage 2
has not been approved yet: wait a few minutes and reload. "wrong or has
expired": make a new token (steps 2 to 5) and paste that one; the set-up asks
up to three times. "lacks the data portability permission": you ticked a
different permission in step 3. "that date has already passed": type the day
the key **expires**, not the day it was made.

#### Send it to GitHub

The daily run on GitHub only learns about LinkedIn once the new values are
there. Right after saving them, the set-up says so and asks `Send them to … on
GitHub now?`: press Enter for yes. It saves just the LinkedIn key, its expiry
date and (the first time) your profile address, never shows a value, and does
not ask for the Claude key again. The Client ID and Client Secret stay on your
computer and in your database: the daily run does not need them.

If you answered **n**, or the GitHub tool is not signed in, it prints
`To send them later, run: uv run tracker setup github`. Run that command, press
Enter when it asks for the Claude key (GitHub keeps the one it has), press Enter
to save, and answer **n** when it offers to start a daily run, unless you want
one now.

**✅ Check:** the list includes `secret LINKEDIN_ACCESS_TOKEN saved`.

**If not:** run `uv run tracker setup github` and read the line where it
stopped.

#### When the key expires

Seven days before the key stops working, the morning summary says so. Run:

```bash
uv run tracker setup linkedin
```

A key is already saved, so the set-up skips stages 1 and 2. If your
application is connected (stage 3), LinkedIn's page opens at once: click
**Allow** (if you are still signed in, LinkedIn may not even ask), then press
Enter to send the new key to GitHub. That is all.

If you connected LinkedIn by hand, before this one-click way existed, the
set-up offers it once: answer **yes** to `Set that up now?` and do steps 1 to
6 of [stage 3](#stage-3-of-3-connect-the-application-to-threadline). Answer
**n** to keep [making the key by hand](#making-the-key-by-hand).

**✅ Check:** you see `LinkedIn made a new key. It works until …` and
`secret LINKEDIN_ACCESS_TOKEN saved`.

**If not:** the same lines as in stage 3's **If not** apply.

### 8b. Refresh now (`tracker setup refresh`)

The dashboard's **Refresh now** button starts one extra, quick update whenever
you want: it reads only what is new and sends no e-mail. This step switches it
on, together with the **on-time morning start** described below. It puts a
small helper called `refresh-now` into your Supabase project. You install
nothing: the set-up does it through Supabase's and GitHub's websites.
It needs a GitHub key, pasted once (nothing shows while you paste), and one
more Supabase sign-in. Neither is saved on your computer.

**Before you start:** your dashboard is ready (part 5) and your private
copy is on GitHub (part 1). If not, the set-up says which step to run first.
Only a private repository you administer counts as your copy: if this folder
still points at the public template, the set-up says
`This folder is not linked to your own private copy on GitHub yet` and stops
before anything is made. Without the GitHub tool it cannot check this, so it
names the repository it will use and asks you to confirm it.

**What you do:** answer **yes** to `Switch on Refresh now for …?` (press Enter),
then do these two things.

**1. The GitHub key.** A GitHub page opens with the name
(`Threadline refresh now`), a one-year expiry date and the permission
**Actions: Read and write** already filled in. Sign in if asked, then:

1. Under **Repository access**, choose **Only select repositories** and pick
   your copy of Threadline (the set-up names it, for example
   `your-name/threadline`). GitHub cannot fill this in for you.
2. Click **Generate token** at the bottom and copy the token (it starts with
   `github_pat_`).
3. Paste it into the set-up. It checks the key can see your workflow, without
   starting anything.

Put the expiry date in your calendar: on that day the button stops working
until you run `uv run tracker setup refresh` again with a new key.

**2. Supabase, once more.** The set-up never saved the sign-in from part 2,
so it asks again, as in
[part 2a](#2a-sign-in-to-supabase-and-your-project-tracker-setup-supabase):
click **Authorize** on the Supabase page and type the code it shows (or paste
a legacy token).

The set-up then saves the helper's settings in Supabase (your GitHub key goes
straight there), puts the helper in place, and checks that it answers.

Last, it switches on the **on-time morning start**. GitHub often starts the
daily run hours after the time you chose; now your Supabase project checks
every 15 minutes and starts it as soon as your time has passed, at most once a
day. GitHub's own schedule stays as a backup and stops by itself when the
day's run already started. It is free and needs nothing more from you
([`refresh-now.md`](refresh-now.md), "The on-time morning start").

**✅ Check:** the set-up says `Refresh now is switched on` and ends with
`On-time morning start is switched on: Supabase starts the daily run at …`
with your time. Open your dashboard and press **Refresh now** (on a phone:
**Refresh**): the line under the header says "Refreshing… new messages will
appear in a few minutes."

**If not:**

- *`GitHub did not accept the token` or `the token cannot see the workflow`:*
  make the key again and check that step 1 picked your copy of Threadline and
  that **Actions** says **Read and write**.
- *`Supabase did not accept the access token` or `Supabase says this access
  token has too little access`:* sign in to Supabase again as in part 2a, or
  make a token with the **Create legacy token** link.
- *`The workflow is switched off on GitHub`:* open the link the set-up shows
  and click **Enable workflow**.
- *The dashboard still says "not switched on yet":* close the dashboard tab and
  open it again (it remembers that answer until the tab is closed).
- *`your database does not have the on-time morning start yet`:* run
  `uv run tracker setup database`, then `uv run tracker setup refresh` again.
- Anything else: the manual way in [`refresh-now.md`](refresh-now.md) does the
  same by hand.

### 8c. The Claude cloud route (`tracker setup cloud`)

Use this instead of the daily run on GitHub only if GitHub does not suit you,
most often because you read **only Outlook**, whose mail programs cannot send
with an app password. A Claude cloud routine sends the summary through Claude's
Gmail connector, so you also need a Google account with Gmail. Do not run both
routes: you would get two e-mails. Once your Claude routine has run once and
the e-mail arrived, switch the GitHub daily run off so both do not run:
`gh workflow disable threadline-run.yml`. At the end of this part the set-up
offers to do it for you, with the answer set to no; answer yes only if the
routine already runs. To do it by hand, or to switch it on again, see "Pause
and resume" in [`operations.md`](operations.md#pause-and-resume).

Set `SUMMARY_DELIVERY=gmail_connector` in `.env` if you also read a Gmail or
other IMAP mailbox: a Claude cloud session can most likely reach only web
addresses, not the mail ports that sending by SMTP needs.

This part is done on <https://claude.ai/code> and cannot be automated from
your computer.

#### Cloud 1. Let Claude open your copy of Threadline

Go to <https://github.com/apps/claude>, install the **Claude** GitHub app, and
give it access to your Threadline copy only.

**✅ Check:** at <https://claude.ai/code> your Threadline copy appears in the list
of repositories.

**If not:** open the Claude app's settings on GitHub and add the repository.

#### Cloud 2. Create the cloud environment

Answer **yes** when the set-up asks whether to set up the Claude cloud routine
instead.

**What the set-up does for you:** it lists the **names** of the variables the
cloud needs (never their values), lists the web addresses the cloud must be
allowed to reach, and offers to put each value on your clipboard in turn so you
never have to open `.env`.

**What you do:**

1. At <https://claude.ai/code>, click the cloud icon with the environment name
   above the message box, then **Add cloud environment**.
2. **Name:** for example `Threadline`.
3. **Network access:** **Custom**. In **Allowed domains**, add one per line the
   domains the set-up printed:
   - `<project-id>.supabase.co`
   - `graph.microsoft.com` (only if you connected Outlook)
   - your mailbox's IMAP server, such as `imap.gmail.com` (only if you
     connected Gmail or another IMAP mailbox)
   - `api.linkedin.com` (only if you connected LinkedIn)

   Reading Gmail and other IMAP mailboxes is not web traffic: it uses port 993.
   Whether a Claude cloud environment lets that through was not checked when
   this guide was written. The doctor in the check below tells you: if its
   `IMAP mailbox` line says the mailbox "did not answer" although the server is
   in the list, use the Mac route (see [`operations.md`](operations.md)).

   Tick **Also include default list of common package managers**. It already
   covers Microsoft's sign-in address, `login.microsoftonline.com`.
4. **Environment variables:** one per line as `NAME=value`. Use the names the
   set-up printed. Usually they are `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_ANON_KEY`, `TOKEN_ENCRYPTION_KEY`, `OWNER_EMAIL_ADDRESSES`, the
   mailbox settings (`MAIL_SOURCES`, `IMAP_PROVIDER`, `IMAP_USERNAME`),
   `OWNER_LINKEDIN_PROFILE_URL`, `LINKEDIN_ACCESS_TOKEN`,
   `LINKEDIN_TOKEN_EXPIRES_ON` and `DASHBOARD_BASE_URL`. For each one, type
   `NAME=`, go back to the terminal and press Enter to get the value onto the
   clipboard, then paste it.
5. Save the environment.

Anyone who can use this environment can read these values, so keep it to
yourself.

**✅ Check:** start a session in this environment, on your Threadline copy, and ask
it to run `cd backend && uv run tracker doctor`. Every line says `ok` (optional
parts may say `skipped`).

**If not:** a `PROBLEM` line says what to fix. "could not be reached" in the
cloud almost always means a missing allowed domain. "missing or wrong" names a
missing variable. Change the environment, then start a **new** session: changes
only reach sessions started afterwards.

#### Cloud 3. Connect Gmail

In Claude, open **Customize → Connectors**, click **+**, choose **Gmail** and
click **Connect**.

**✅ Check:** Gmail is listed as connected.

**If not:** disconnect it and connect it again, making sure you allow sending.

#### Cloud 4. Create the routine

1. Go to <https://claude.ai/code/routines> and click **New routine**.
2. **Name:** for example `Threadline daily run`.
3. **Repository:** your Threadline copy. **Environment:** the one from Cloud 2.
4. **Prompt:** `Run the daily-run command from this repository.`
5. **Connectors:** keep **Gmail**, and **remove every other connector**. In a
   routine, connectors act without asking you first. Gmail can send e-mail, so
   leave nothing attached that the job does not need.
6. **Schedule:** daily, at a time a few minutes past the hour, for example
   **07:07** (times are in your own time zone).
7. Save, then click **Run now** once.

**✅ Check:** within about ten minutes, the summary e-mail arrives in your
inbox, and the dashboard's **Daily runs** page shows the run as **Worked** or
**Partly worked**.

**If not:** a green routine status only means the session ran, not that the job
worked. Open the session and read its last message. Then run
`uv run tracker doctor` on your computer: it names what is wrong, one line
each.

### 8d. Your own dashboard on Netlify (`tracker setup dashboard`)

Only if you would rather not use the shared dashboard. The set-up publishes
your own copy on Netlify, for free, at an address such as
`https://threadline-xxxxxx.netlify.app`. You need a free Netlify account and
one Netlify token.

**What you do:**

1. Run `uv run tracker setup dashboard`. When it asks which dashboard to use,
   choose your own copy on Netlify.
2. It asks whether you already have a Netlify account. If not, answer **n**:
   Netlify's sign-up page opens. **Sign up with GitHub** is quickest. If
   Netlify answers "Email address is invalid", your GitHub e-mail address has a
   "+" in it, which Netlify refuses: use **Sign up with email** instead, with
   any address you can read. Press Enter in the terminal once you are signed
   in.
3. Netlify's token page opens. Click **New access token**, name it
   `Threadline set-up`, choose the shortest expiry offered, click
   **Generate token** and copy it. The page may look slightly different.
4. Paste the token into the terminal. It stays hidden and is never saved.

**What the set-up does for you:** it downloads the ready-made dashboard, adds
your project's address and its public key, and publishes it. It saves the
address so the morning e-mail links to it, and points Supabase's sign-in link
at it. Netlify's free plan is enough.

Three things happen behind the scenes that are good to know:

- The GitHub command-line tool must be signed in for the ready-made dashboard,
  because the set-up uses it to check who built the download. If it is not, the
  step prints `Run 'gh auth login'`: do that, then run the step again.
- Before publishing, the step checks that the download was built by this
  project's own release workflow (GitHub keeps a signed record of that, called a
  build attestation). If the check fails, **nothing is published**. When Node.js
  22 or newer is installed, the step then offers to build the dashboard on your
  computer instead; answer yes.
- The dashboard's security settings (its security headers and its redirect
  rule) come from the set-up itself and never from the download.

**✅ Check:** on your phone, open the new address, type your e-mail, and click
the link in the e-mail Supabase sends. Your dashboard opens.

**If not:** the lines of part 5's **If not** apply here too.

**If it says Netlify keeps your dashboard private.** Netlify accounts made
since July 2026 keep every new site private, so only you, signed in to Netlify,
can open it, and your phone cannot. Netlify gives the set-up no way to change
that, so the set-up stops, opens your project's page on Netlify and lists the
clicks. You do them once:

1. Open your project (`threadline-xxxxxx`) if it is not open already.
2. Click **Project configuration → General → Visitor access**.
3. Under **Project visibility**, click **Edit visibility**. If Netlify asks,
   choose **Customize this project's visibility**.
4. Set **Production** to **Public** (leave the previews as they are) and click
   **Save**.
5. Run `uv run tracker setup dashboard` again.

This is safe: the dashboard has its own sign-in, and only your e-mail address
can open your data.

**✅ Check:** the step now says `Check: https://threadline-xxxxxx.netlify.app
opens the dashboard.`

**If not:** if Netlify does not offer **Public**, your team is set to keep
every project private: change it in **Team settings → General → Visitor access
→ Default project visibility**, then do the steps above again.

If you set `NETLIFY_SITE_ID` in `.env` yourself, it must be a Netlify site ID or
a plain site name, nothing else.

If the step warns that the downloaded dashboard is **newer than your copy of
Threadline**, the dashboard expects database changes your copy does not have
yet, and it may show errors. The safe way out is to publish the dashboard from
your own copy with a local build: run
`uv run tracker setup dashboard --build-here` (this needs Node.js 22 or
newer).

Your own copy stays as it was when it was published. To publish a newer one,
for example after you updated Threadline, run `uv run tracker setup dashboard`
again.
