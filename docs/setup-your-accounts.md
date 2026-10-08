# Setting it up: from nothing to your first morning summary

> **Would you rather not do this yourself?** Claude can run every command in
> this guide for you while you create the accounts and click where it says:
> see [`setup-with-claude.md`](setup-with-claude.md). It is one sentence to
> paste into the Claude app.

This guide takes you from nothing to the first summary e-mail, one small step at
a time. You do not need to know how to program. Where something can be done for
you, the tool does it (`uv run tracker setup`). Where only you can do it, such
as creating an account or clicking "Allow", this guide says exactly what to
click.

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
| A **Mac or a Linux** computer with a terminal | to run the set-up once. **Windows is not supported.** | – |
| A paid Claude plan: **Pro, Max or Team** | runs the daily job on GitHub with your own subscription, with your laptop shut. The daily run uses part of your plan's usage limits, like any other use of Claude | your existing plan |
| **Claude Code** installed on that computer | makes the key that lets GitHub use your Claude plan (`claude setup-token`). Install it from the official page, <https://code.claude.com/docs/en/setup>, and sign in once | included in your plan |
| A GitHub account | runs Threadline every day from your private copy (GitHub Actions) | free (2,000 minutes a month for private copies at the time of writing; a month of runs uses about 150–300) |
| *Optional, recommended:* the GitHub command-line tool `gh` (<https://cli.github.com>) | signs you in to GitHub for the download in part 1 and lets the set-up create your private copy and save your settings for you | free |
| A Supabase account | the database that keeps your people and conversations | free plan |
| A Vercel account | publishes the dashboard so it opens on your phone | free "Hobby" plan, personal use only |
| At least one mailbox: Gmail, Outlook.com/Hotmail, iCloud, Yahoo, Fastmail or any mailbox that offers IMAP | the mail Threadline reads, read-only; Gmail and the others also send you the summary (with only Outlook, see the alternative route at the end) | free (Fastmail: a paid plan above Basic) |
| *Optional:* a Microsoft personal account (Outlook.com, Hotmail, Live) | the calendar, which is read from Outlook only for now | free |
| *Optional:* a LinkedIn account | reads your LinkedIn messages too (only for members located in the EEA or Switzerland, see below) | free |
| *Optional:* [Node.js](https://nodejs.org) 22 or newer | only for the manual way of switching on the dashboard's Refresh now button ([`refresh-now.md`](refresh-now.md)); the guided way needs nothing | free |
| *Optional:* an Azure account | only if you want your own Microsoft application instead of the public one (see "Your own Microsoft application" in part 5) | free |

**Check Claude Code now.** In Terminal, type:

```bash
claude --version
```

**✅ Check:** it prints a version number.

**If not:** `command not found` means Claude Code is not installed yet, or
Terminal was not reopened after installing it. Follow the official install page
above, close Terminal, open it again and retry. Then type `claude` once and
sign in with your Claude plan.

**The LinkedIn limit.** LinkedIn lets only members whose profile is located in
the **European Economic Area or Switzerland** export their messages this way.
If you live elsewhere, skip LinkedIn: everything else works without it.

**The sign-in e-mail limit.** You will sign in to the dashboard with a link that
Supabase e-mails to you. Supabase's built-in e-mail only reaches the address
your Supabase account was registered with (or members of your Supabase
organisation), unless you set up your own sending service ("custom SMTP"). Part 2
explains what that means for you.

**Time.** About an hour and a half the first time, most of it creating accounts
and copying values from one screen to another. You can stop at any point:
`uv run tracker setup` carries on where you left off.

**What it costs.** No other paid service is needed. Supabase, Vercel, GitHub,
Google, Microsoft and LinkedIn are all used on their free plans; the only
exception would be a paid mailbox you choose yourself, such as Fastmail.
Free-plan limits change, so check the providers' pricing pages if in doubt.

**Your keys.** Every key you paste is saved in a file called `.env` in the
project folder, readable only by you. Never paste a key into a chat, an e-mail
or a document.

**On Linux.** This guide was written on a Mac. On Linux, the Mac keyboard
shortcuts it gives (such as ⌘ + N for a new Terminal window) are your desktop's
own, and the set-up cannot reach your clipboard: wherever it would put a value
on the clipboard, it says `No clipboard is available here` and you copy the
value from `.env` (or the file it names) yourself. Everything else is the same.

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
  official way the set-up talks to Supabase on your behalf, with a token you
  make and delete afterwards.
- A **CRM** is customer-relationship software, which Threadline is not.
- The **EEA** is the European Economic Area: the EU plus Iceland, Liechtenstein
  and Norway.

---

## 1. Get Threadline onto your computer

1. Sign in to <https://github.com>. Open this project's page, click
   **Use this template** → **Create a new repository**, give it a name, choose
   **Private**, and click **Create repository** (the page may look slightly
   different). A private copy keeps your settings and changes to yourself.
2. Open **Terminal** (on a Mac: press ⌘ + Space, type `Terminal`, press Return).
3. Install **uv**, the tool that runs Threadline. Paste this line and press
   Return:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Then close Terminal and open it again.
4. Download your copy. GitHub no longer accepts your account password for
   this, so the easiest way is the GitHub command-line tool. Download the
   installer from <https://cli.github.com> (on a Mac: the `.pkg` file), open
   it, then sign in once. Choose **GitHub.com**, **HTTPS**, say **yes** to
   authenticating Git, and **Login with a web browser**:

   ```bash
   gh auth login
   ```

   Then download your copy. Replace `<your-user>` with your GitHub name and
   `<your-copy>` with the name you gave the copy in step 1:

   ```bash
   gh repo clone <your-user>/<your-copy> tracker
   cd tracker/backend
   uv sync
   ```

   *Without the GitHub tool:* `git clone https://github.com/<your-user>/<your-copy>.git tracker`
   also works, but when it asks for a password, do not type your GitHub
   password: it will be refused. Sign in through the browser window that
   Git's credential helper opens instead, or paste a personal access token
   (GitHub: **Settings → Developer settings → Personal access tokens**).
   Installing `gh` and running `gh auth login` first avoids all of this.

**✅ Check:** `uv run tracker --help` prints a list of commands that includes
`setup` and `doctor`.

**If not:** if the Mac asks to install "command line developer tools", click
**Install**, wait, then repeat step 4. If `gh` says `authentication required`
or `Repository not found`, run `gh auth login` again and check the spelling of
your user and copy names. If it says `uv: command not found`, close
Terminal, open it again and repeat step 4.

**Where to type the commands.** Every `uv run tracker …` command in this guide
is typed in Terminal inside the `backend` folder of your copy. Terminal opens
in your home folder, where step 4 put the copy, so in every new Terminal window
type this first (it works from any folder):

```bash
cd ~/tracker/backend
```

**✅ Check:** the last line in Terminal, the one before your cursor, ends with
`backend`.

**If not:** `Failed to spawn: tracker` or `No such file or directory` means
Terminal is in another folder: type `cd ~/tracker/backend` and try again. If
you gave the folder another name in step 4, use that name instead of
`tracker`. (The `git` lines the set-up prints work from any folder of the
project.)

---

## 2. Create your Supabase project

Supabase is the database. This part cannot be automated: the project must
belong to your own account.

1. Go to <https://supabase.com> and click **Start your project**. Sign in with
   GitHub, or with your e-mail address.
2. Click **New project**.
   - **Name:** anything, for example `tracker`.
   - **Database password:** click **Generate a password**. You will not need it
     for Threadline, but keep it in your password manager.
   - **Region:** the one closest to you.
   - **Plan:** **Free**.
3. Click **Create new project** and wait about two minutes.

**✅ Check:** the project's home page opens and no longer says it is being set
up.

**If not:** wait a few more minutes and reload the page. If it still shows an
error, delete the project and create it again.

**Important: which e-mail address you sign in with.** You will sign in to the
dashboard with a link Supabase e-mails to you. Supabase's built-in e-mail sends
only **two messages an hour**, and **only to the address your Supabase account
was registered with (or to members of your Supabase organisation)**. So later,
when the set-up asks for your dashboard e-mail, use the same address you signed
up to Supabase with. (Using another address needs your
own e-mail sending service, called "custom SMTP" in Supabase. This guide does
not cover it.)

---

## 3. Connect Supabase and build the database

Now start the guided set-up. It runs the steps of parts 3 to 6 in order, and
you can stop it at any time with Ctrl + C. Everything it has saved stays saved.

```bash
uv run tracker setup
```

**Prefer a page to the terminal?** Add `--browser`:

```bash
uv run tracker setup --browser
```

A page called *Threadline set-up* opens in your browser and asks the same
questions, one at a time, with keys in hidden fields and a **Continue** button
where this guide says "press Return". The page is served to your computer
only (its address starts with `http://127.0.0.1:`). The terminal still shows
what is asked, never what you answer. A **Stop for now** link at the bottom
ends the set-up cleanly; everything saved stays saved. `--browser` works with a
single step too, for example `uv run tracker setup database --browser`.

The full set-up goes through these steps in this order: `supabase`,
`encryption`, `database`, `login`, `categories`, `timezone`, `mailbox`,
`microsoft`, `linkedin`, `dashboard`, `schedule`, `github`, `refresh` (and
`cloud`, only for the alternative route). This guide follows the same order,
with one detour: the dashboard needs Vercel, which comes in part 7.

**The first time you run it:** carry on through parts 3 to 6 as the set-up asks.
When it reaches `Is the dashboard published already?`, answer **no**: the
set-up stops there by itself, because the steps after it need the dashboard's
address. Do part 7 (Vercel), then run `uv run tracker setup` again: it skips
what is already done and carries on from the dashboard through the steps of
part 8.

**✅ Check:** after you answer **no**, you see `Stopped: the dashboard is not
published yet - publish it first (part 7 of the guide).` and then `Fix that,
then run 'uv run tracker setup' again: finished steps are kept and it carries
on from here.`

**If not:** if you answered **yes** by mistake, it asks for the address: press
Ctrl + C to stop. Nothing is lost; carry on from part 7.

To run one step again later, name it, for example
`uv run tracker setup database`.

### 3a. The address and the two keys (`tracker setup supabase`)

**What the set-up does for you:** it opens the right Supabase page, asks for the
three values, checks each one with Supabase straight away, and saves them. The
secret key is typed hidden and never shown.

**What you do:**

1. When it asks for the **project address**, open **Project Settings** (the cog)
   → **General**, copy the **Project ID** and paste it. The set-up turns it into
   `https://<project-id>.supabase.co` for you.
2. The set-up opens **Project Settings → API Keys**, tab **Publishable and
   secret API keys**. Copy the **Publishable key** (it starts with
   `sb_publishable_`) and paste it.
3. On the same page, under **Secret keys**, click the eye icon, copy the key
   (it starts with `sb_secret_`) and paste it. Nothing appears on screen while
   you paste: that is on purpose.

**✅ Check:** you see `Supabase accepted the address and both keys.`

**If not:** "did not accept the publishable key" means the address and the key
belong to different projects, or the key was cut short: copy it again with the
copy icon. "refused the secret key" usually means the publishable key was pasted
there by mistake.

### 3b. The encryption key (`tracker setup encryption`)

**What the set-up does for you:** everything. It makes a key that locks your
Microsoft sign-in and your mailbox's app password inside the database, and
saves it without showing it.

**✅ Check:** you see `A new key was made and saved.` (or, on a second run,
`A usable key is already saved; it is kept.`)

**If not:** if it asks whether to replace an existing key, answer **no** unless
you know the old one is wrong. A new key means signing in to Microsoft again.

### 3c. The database structure (`tracker setup database`)

**What the set-up does for you:** it looks at your database, lists the structure
files that are missing (and any whose effect it cannot see and that may not have
run yet: running one of those a second time is harmless), and applies them for
you through Supabase's official
Management API. For that it needs a **personal access token**, which you paste
once. The token is used for this step only and **never saved**.

**What you do:**

1. Answer **yes** to "Apply them automatically?".
2. On the page that opens (**Account → Access Tokens**), click **Generate new
   token**, give it any name, choose the shortest expiry offered, and leave the
   access as Supabase offers it: the set-up needs to read and write the
   database's **migrations** (its structure files). Copy the token. (The page
   may look slightly different.)
3. Paste it into Terminal. Once the step is done, delete the token on the same
   Supabase page.

The files go one at a time, a second or two apart, so this takes about half a
minute. If Supabase refuses a file, the set-up shows Supabase's reason in one
line and tries that file once more by itself.

**✅ Check:** the step starts with `To apply: 0001_schema, 0002_access_rules, …`,
naming every file still missing (all of them on a new project). Then you see
`Applied 0001_schema`, one line per file, and `The database structure is in
place.`

**If not:** if you prefer not to create a token, or a file still fails, the
set-up switches to the manual route by itself: it opens the **SQL Editor**, puts
each file on your clipboard in turn, and waits. For each file: click **+** for a
new query, paste, click **Run**, wait for `Success. No rows returned`, and only
then press Return in Terminal. Pressing Return is not enough on its own: the
set-up checks that the file really ran, and if it did not, it says
`The database does not show … yet` and gives you the same file again. At the
end it checks the database once more. If it still lists a file as missing, run
`uv run tracker setup database` again.

---

## 4. Your dashboard login, categories and time zone

### 4a. Your dashboard login (`tracker setup login`)

The dashboard only lets in the one login recorded as its owner. Nobody else can
create a login, so nobody else can read your data.

**What the set-up does for you:** it creates your login, records it as the only
owner, and checks that sign-ups are switched off.

**What you do:**

1. Type the e-mail address you signed up to Supabase with (see the warning in
   part 2). If you signed in to Supabase with GitHub, it is the main e-mail
   address of your GitHub account; Supabase shows it under **Account →
   Preferences**.
2. If it says "Sign-ups are still open", the page **Authentication → Sign In /
   Providers** opens. Switch off **Allow new users to sign up**, click **Save**,
   and press Return in Terminal.

**✅ Check:** you see `… can now sign in to the dashboard` and `Sign-ups are
switched off: nobody else can create a login.`

**If not:** if the switch keeps coming back on, reload the Supabase page, switch
it off again and click **Save** before pressing Return.

### 4b. Your categories (`tracker setup categories`)

Threadline puts each person you talk to in a category, such as "Startup" or
"Investor". Here you choose those categories. This step is optional: skip it
and you keep the job-search categories, which you can change any time on the
dashboard's **Settings** page.

**What the set-up does for you:** it saves your categories to your database and
tells the AI helper about them.

**What you do:**

1. Answer **y** to "Choose your categories now?" (or **n** to skip).
2. Type the number of the list closest to what you track, for example `3` for a
   job search or `5` for sales. Press Return to accept the number it suggests.
3. It lists the suggested categories and asks "Use all of them?". Press Return
   to keep them all. If you type `n`, it asks about each one: press Return to
   keep it, or type `n` to drop it.
4. To add one of your own, answer **y**, then type its name ("Supplier"), a
   name for a group (press Return to accept "Suppliers"), who belongs there in
   one sentence ("Companies that sell to us") and a colour (press Return to
   accept the one offered). The sentence matters: the AI helper reads it to
   decide who goes where. Answer **n** when you have no more to add.
5. Look at the list it shows, then press Return to save it.

**✅ Check:** you should now see `Saved … categories, 'Not known' included.`
Once the dashboard is published (part 7), its **Settings** page shows the same
categories.

**If not:** "That did not work" means a name was empty, too long, already in
your list, or the colour was not one of those offered: type it again. If you
answered **n** by mistake, run `uv run tracker setup categories` again.

### 4c. Your time zone (`tracker setup timezone`)

**What the set-up does for you:** it reads the time zone your computer uses and
offers it, such as `Your time zone [Europe/Paris]:`. Your time zone decides what
"today" is for due dates and the summary, and the daily run's time (part 8) is
read in it. It is saved as `OWNER_TIME_ZONE` and later sent to GitHub with your
other settings. When the zone differs from the one in the daily run's workflow
file (`.github/workflows/threadline-run.yml`), it writes the new zone there
too, keeping the time, shows the line it changed and offers to save it in git
for you, exactly as in part 8b.

**What you do:**

1. Press Return to keep the zone offered, or type yours in the same form
   (`America/New_York`, `Asia/Tokyo`, `UTC`). Capital letters do not matter:
   `europe/rome` is accepted and saved as `Europe/Rome`.
2. It then asks for your name as people write it (such as `Sam Rivera`). This
   is optional: it helps only when your e-mail address does not spell your name
   (`jd123@…`). Press Return to skip it.

**✅ Check:** you see `Saved OWNER_TIME_ZONE=…` with your zone.

**If not:** "that is not a time-zone name" means it was typed in another form:
use the region and the city with a slash, such as `Europe/Rome`. To change it
later, run `uv run tracker setup timezone`.

---

## 5. Your mailbox and calendar

Threadline needs **at least one mailbox**: Gmail, Outlook.com/Hotmail, iCloud,
Yahoo, Fastmail, or any other mailbox that offers IMAP. It only ever reads:
nothing is sent, moved, deleted, or even marked as read.

**The calendar is read from Outlook only, for now.** With Gmail alone,
Threadline reads your e-mail — including interview invitations that arrive by
mail — but not your Google Calendar.

### 5a. Choose your mailbox (`tracker setup mailbox`)

The set-up asks: *Which mailbox should Threadline read? gmail, outlook, icloud,
yahoo, fastmail or other*. Type one word and press Return.

- **outlook** (also for Hotmail and Live): go on to
  [5c](#5c-outlook-mailbox-and-calendar-tracker-setup-microsoft). Good to know
  now rather than in part 8: with Outlook alone, the run on GitHub cannot
  e-mail you the morning summary, because Microsoft allows no app password for
  sending. Connect a Gmail or other mailbox as well (run
  `uv run tracker setup mailbox` again later), or use the
  [alternative route](#alternative-the-daily-run-in-a-claude-cloud-routine).
- **anything else**: follow 5b below for your provider.

**✅ Check:** the set-up either asks for your address (5b) or says the Microsoft
step signs you in (5c).

**If not:** if it says "please answer gmail, outlook, …", type one of those
words exactly.

### 5b. Gmail (or another mailbox)

Gmail, iCloud, Yahoo and Fastmail do not let other programs use your normal
password. Instead you make an **app password**: a separate password just for
Threadline, which you can remove at any time. Your normal password is never
given to Threadline.

**What the set-up does for you:** it asks for your address, explains app
passwords, opens your provider's page, and waits for you to paste the new
password (nothing is shown while you paste). Then it **checks it live**: it
signs in, opens your inbox read-only, counts the messages of the last 30 days
and looks for your Sent folder. Only then does it store the password —
encrypted, in your database, **never in `.env`** — and offer to add the
address to your own addresses.

**✅ Check (for every provider):** Terminal shows
`Connected. Your inbox has … messages from the last 30 days.`, then
`Your own replies are read from the folder '…'.` and
`Saved the app password, encrypted, in your database - it is not in .env.`

**If not:** "refused the app password" means the password was copied wrongly,
belongs to another address, or the account does not allow app passwords — see
your provider below. The set-up lets you paste again twice. "No Sent folder was
found" still works, but your own replies will not be read: tell the project
which folder your mail program saves sent mail in.

#### Gmail

1. **Turn on 2-Step Verification.** Open <https://myaccount.google.com/security>,
   find **2-Step Verification** and follow Google's steps (you need your phone).
   The page may look slightly different.

   **✅ Check:** the Security page shows 2-Step Verification as **on**.

   **If not:** finish Google's steps; app passwords appear only once it is on.

2. **Make the app password.** Type `gmail` and your Gmail address in Terminal.
   The set-up opens <https://myaccount.google.com/apppasswords>. Sign in if
   asked, type a name such as `Threadline`, and create it. The page may look
   slightly different.

   **✅ Check:** Google shows a 16-character password. Copy it now: Google shows
   it only once.

   **If not:** if Google says the setting is not available, one of these is
   true: 2-Step Verification is off; you sign in only with security keys;
   Advanced Protection is on; or it is a work or school account whose
   administrator switched app passwords (or IMAP) off. Only the administrator
   can change the last one — use Outlook instead, or ask them.

3. **Paste it in Terminal** and press Return. Spaces do not matter.

   **✅ Check:** the lines of the general check above, with the folder
   `[Gmail]/Sent Mail` (or its name in your language).

   **If not:** make a new app password and paste that one.

Good to know: IMAP is always on for personal Gmail accounts, so there is no
setting to switch on. **Changing your Google password removes every app
password** — see "Renew a mailbox app password" in
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

3. **Paste it in Terminal.**

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

2. **Paste it in Terminal**, then click **Done** on Yahoo's page.

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

2. **Paste it in Terminal.** Wait for the check to pass before clicking
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

2. Type `other`, then the server, the port (press Return for 993), the name
   you sign in with (usually your address), and paste the password.

3. Once your mailbox is saved, the set-up asks for the **sending server**
   (SMTP), which it needs to
   e-mail you the morning summary from this mailbox (the usual way; it skips
   this when you chose another way to send the summary). Your provider's help
   pages list it next to the IMAP server. It suggests a name (for
   `imap.example.com` it offers `smtp.example.com`): press Return to accept
   it, or type the right one. Then type the port, **465** or **587** (press
   Return for 465). The set-up signs in to that server once with the same
   app password, to catch a wrong server now rather than every morning. It
   sends nothing.

   **✅ Check:** after the general check above, you see
   `Signed in to the sending server. Nothing was sent.`

   **If not:** "did not answer" means the server name or port is wrong, or the
   provider does not offer it over TLS on that port. The set-up asks
   `Try another server or port?`: press Return to try again, or type `n` to
   carry on without it for now. After three tries it carries on by itself.
   Either way your mailbox stays connected and is read every morning; only the
   morning summary cannot be e-mailed yet. Check the name and port in your
   provider's help pages, then run `uv run tracker setup mailbox` again: it
   asks for the app password once more (make a new one if you no longer have
   it) and then for the sending server. If your daily run is on GitHub, run
   `uv run tracker setup github` after that, so the run there is told the
   sending server too. A sending server saved for a different mailbox is
   removed at this point, so the summary is never sent through the wrong one.
   Later, `uv run tracker doctor` shows a **Summary e-mail** line for the
   sending server.

### 5c. Outlook mailbox and calendar (`tracker setup microsoft`)

If you chose another mailbox in 5a, this step asks first whether to connect
Outlook as well. Answer **no** to skip it; you can add it later with
`uv run tracker setup microsoft`.

**What the set-up does for you:** it asks Microsoft for a short one-time code,
opens Microsoft's page, waits while you sign in, stores the resulting key
encrypted in your database, and reads your calendar once to show who signed in.
From then on the key renews itself every day.

**What you do:**

1. Type the code shown in Terminal on the Microsoft page that opens.
2. Sign in with your Outlook.com or Hotmail account.
3. Microsoft lists the permissions: **read your mail**, **read your calendars**,
   and **keep access**. All are read-only. Click **Accept** (or **Yes**).
4. Back in Terminal, answer **yes** when it offers to save the signed-in address
   as one of your own.

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

## 6. LinkedIn (optional; EEA and Switzerland only)

This is the least friendly step in the guide, because LinkedIn offers no
sign-in button for it: you make a key by hand on LinkedIn's developer pages.
Before you decide, here is what to expect:

- **It is optional.** Everything else works without LinkedIn, and you can add
  it later with `uv run tracker setup linkedin`.
- **It depends on where your LinkedIn profile is located.** LinkedIn offers
  this only to members whose profile is located in the European Economic Area
  or Switzerland. It is the location on your profile that counts, not your
  citizenship.
- **LinkedIn messages appear a day or two late.** LinkedIn's copy of your
  messages runs one to two days behind (measured on 24 September 2026), so a
  message you receive on LinkedIn today shows up in Threadline tomorrow or the
  day after. Nothing is lost; it only arrives later.
- **It takes about ten minutes.** When the key expires you repeat only the last
  part (6c and 6d).

<!-- The one-to-two-day delay is recorded beside LINKEDIN_OVERLAP_DAYS in
     backend/src/tracker/shared/constants/collection.py. -->

**What the set-up does for you (`tracker setup linkedin`):** it takes you
through three stages in order, opens the right LinkedIn page for each one and
waits while you click. Then it makes one small call to LinkedIn with your new
key and saves the key only if LinkedIn accepts it.

**What you do:** answer **yes** to "Connect LinkedIn now?" (or press Enter to
skip LinkedIn), then follow 6a to 6d as the pages open.

### 6a. Create the developer application

**Stage 1 of 3.** The set-up opens <https://www.linkedin.com/developers/apps>.

1. Click **Create app**.
2. **App name:** anything, for example `Threadline`.
3. **LinkedIn Page:** choose the page LinkedIn suggests for this product,
   **Member Data Portability (Member) Default Company**. Do **not** create a new
   page.
4. Tick the terms and click **Create app**.
5. Go back to the terminal and press Enter.

**✅ Check:** your new application's page opens with tabs such as **Settings**,
**Auth** and **Products**.

**If not:** if LinkedIn asks you to verify the page, make sure you picked the
default company named above. If you already created the application on an
earlier try, do not make a second one: click it in the list instead.

### 6b. Add the Member Data Portability product

**Stage 2 of 3.** Stay on your application's page, the one stage 1 ended on.

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

### 6c. Make the key

**Stage 3 of 3.** The set-up opens LinkedIn's token page,
<https://www.linkedin.com/developers/tools/oauth/token-generator>. In
LinkedIn's own menu it is **Docs and tools → OAuth Token Tools → Create token**.

1. Pick your application.
2. Tick the permission (scope) whose name starts with **`r_dma_portability`**.
   LinkedIn's own pages name it slightly differently in different places.
3. Click **Request access token**, sign in if asked, and click **Allow**.
4. Copy the token LinkedIn shows. It is shown only once.
5. Paste it in the terminal and press Enter. Nothing appears as you paste; that
   is on purpose.

**✅ Check:** you see `LinkedIn accepted the key.`

**If not:** if **Request access token** is greyed out, the product from 6b has
not been approved yet. Wait a few minutes and reload. "wrong or has expired":
make a new token (steps 1 to 4) and paste that one; the set-up asks up to three
times. "lacks the data portability permission": you ticked a different
permission in step 2.

### 6d. The expiry date and your profile address

The key stops working on a fixed day, and only LinkedIn can tell you which. The
set-up asks for that day so the morning summary can remind you **seven days**
before it comes.

1. At the top of the same LinkedIn page, open **Docs and tools → OAuth Token
   Tools** and choose the **Token Inspector** (the page may look slightly
   different).
2. Pick your application, paste the token and click **Inspect**. Find the day
   the token expires.
3. Type that day in the terminal. `2027-09-24`, `24 Sep 2027`,
   `24 September 2027` and `Sep 24, 2027` all work. A date written only with
   numbers and slashes, such as `03/04/2027`, is refused, because it could mean
   two different days.
4. Paste your profile address (`https://www.linkedin.com/in/…`). The set-up
   asks for it only the first time.

**✅ Check:** you see `Saved LINKEDIN_ACCESS_TOKEN in .env.`, then the same line
for `LINKEDIN_TOKEN_EXPIRES_ON` and `OWNER_LINKEDIN_PROFILE_URL`.

**If not:** "that date has already passed": you typed the day the token was
made, or the wrong year. Type the day it **expires**.

**When the key expires.** Run `uv run tracker setup linkedin` again. A key is
already saved, so the set-up skips 6a and 6b and goes straight to 6c. The steps
are in [Renew the LinkedIn key](operations.md#renew-the-linkedin-key).

---

## 7. Publish the dashboard (Vercel)

The dashboard is a web page. Publishing it on Vercel lets you open it on your
phone.

1. Sign in to <https://vercel.com> with GitHub.
2. Click **New Project** and import your copy of Threadline (the labels may
   read **Add New… → Project** and **Import Git Repository**; the page may look
   slightly different).
3. On the page before **Deploy**:
   - **Root Directory:** click **Edit** and choose **`frontend`**. This is easy
     to miss, and nothing works without it. If Vercel instead says
     *"Multiple applications detected"* and lists **backend** and **frontend**,
     click **Import single project** next to **frontend** (marked *Vite*): that
     sets the folder for you.
   - **Environment Variables:** add two. These are the address and the
     **Publishable key** from part 3a: **Supabase → Project Settings → API
     Keys**.
     - `VITE_SUPABASE_URL` = your project address (`https://<project-id>.supabase.co`)
     - `VITE_SUPABASE_ANON_KEY` = your **publishable** key (it starts with
       `sb_publishable_`). Never the secret one.
4. Click **Deploy** (or **Create Project**, then **Deploy**) and wait for it to
   finish. If Vercel only says *"Project created … then deploy"* and nothing
   starts, open the project and choose **Deployments → Redeploy**, or push any
   change to your copy: every push publishes the dashboard again.
5. Open the project's **Settings → Domains** and copy the **production
   address**, which looks like `https://<name>.vercel.app`.

**About Vercel's login wall.** New Vercel projects protect every address except
the production one with a Vercel login. Always use the production address from
the **Domains** tab and you will not meet it. You only need to change
**Settings → Deployment Protection** if you want other addresses to open too.

**✅ Check:** the production address opens the dashboard's sign-in page in a
private browser window.

**If not:** a Vercel sign-in page means you opened a different address: use the
one from **Domains**. A blank page or "missing settings" means the two
environment variables are missing or misspelt: fix them, then in **Deployments**
choose **Redeploy** (changed variables only apply after a redeploy).

### 7a. Tell Threadline and Supabase (`tracker setup dashboard`)

Back in Terminal, in the `backend` folder, start the set-up again:

```bash
uv run tracker setup
```

It skips every finished step (an optional step you skipped before, such as
LinkedIn, is offered once more: answer **n** to skip it again) and asks
`Is the dashboard published already?`. Answer **yes** this time, and paste the
production address from step 5. (To redo only this step later:
`uv run tracker setup dashboard`.)

**What the set-up does for you:** it opens the address once to check it shows
the dashboard (and not a Vercel login), saves it so the morning e-mail links to
it, and opens Supabase's **Authentication → URL Configuration** page.

**What you do on that Supabase page:**

- **Site URL:** your production address.
- **Redirect URLs:** add your production address followed by `/**`.
- Click **Save**, then press Return in Terminal.

**✅ Check:** you see `Saved DASHBOARD_BASE_URL in .env.`, and the set-up goes
straight on to `Step 11 of 14: The daily time (GitHub Actions)`, which is part
8b. Later, on your phone, open the address, type your e-mail, and click the
link in the e-mail Supabase sends: the dashboard opens (it is empty until the
first run).

**If not:** "Email address not authorized" means the address is not the one of
your Supabase account (see part 2). A link that opens `localhost` means the
Site URL was not saved.

---

## 8. Run it every day on GitHub

Every morning GitHub starts Threadline on your private copy, runs the daily
job with **your own Claude subscription**, and e-mails you the summary from
your own mailbox, with your laptop shut. At the time of writing, GitHub's
free plan includes 2,000 minutes a month for private repositories; one run takes
about five to ten minutes, so a month of mornings uses roughly 150 to 300.

The set-up you restarted in 7a carries on here by itself, in this order: the
daily time (8b), your settings on GitHub (8c) and Refresh now (8f). It ends
with the doctor's check of every connection. The command under each of those
headings runs that one step again on its own, later. Parts 8a, 8d and 8e are
done on the GitHub website once the set-up has finished.

**Which mailbox sends the summary.** Threadline sends it from the Gmail,
iCloud, Yahoo, Fastmail or other mailbox you connected in part 5, with the same
app password (no new password to make). If you connected **only Outlook**, it
cannot: Microsoft requires its own sign-in method (OAuth2) for Outlook.com,
Hotmail and Live mail programs, and turned off plain passwords and app
passwords for them in September 2024. You have two choices: connect a Gmail or
other mailbox as well in part 5 (Threadline can read both), or use the
[alternative route](#alternative-the-daily-run-in-a-claude-cloud-routine),
which sends through Claude's Gmail connector.

### 8a. Turn on GitHub Actions for your copy

Open your Threadline copy on <https://github.com> and click the **Actions**
tab. If GitHub shows a button such as **I understand my workflows, go ahead
and enable them**, click it.

**✅ Check:** the Actions tab lists a workflow called **Threadline run**.

**If not:** open **Settings → Actions → General**, choose **Allow all actions
and reusable workflows**, click **Save**, and open the Actions tab again.

### 8b. Choose the time (`tracker setup schedule`)

The set-up reaches this step right after the dashboard. To run it on its own
later:

```bash
uv run tracker setup schedule
```

**What the set-up does for you:** it asks what time the run should start,
reads it in the time zone you gave in part 4c, writes both into the workflow
file `.github/workflows/threadline-run.yml`, and shows you the two lines it
changed. GitHub follows your summer and winter time by itself. To use a
different zone, run `uv run tracker setup timezone`: it updates the workflow's
zone too. This step then asks whether to
run `git add`, `git commit` and `git push` for you; it only does so after you
answer yes.

A time a few minutes past the hour (such as **07:07**) starts more reliably:
GitHub is busiest on the hour and may start a run a few minutes late.

**✅ Check:** on GitHub, open `.github/workflows/threadline-run.yml` in your copy.
The `cron:` line shows your minute and hour (`7 7 * * *` for 07:07), and the
`timezone:` line shows your zone.

**If not:** the change was not pushed yet. In Terminal, run the `git` lines the
set-up printed (they work from any folder of the project). If Terminal answers
*Please tell me who you are*, git does not know your name yet: run
`git config --global user.name "Your Name"` and
`git config --global user.email you@example.com` once, with your own name and
address, then run the `git` lines again. If the set-up said
`This folder is not linked to a copy of yours on GitHub yet`, carry on with 8c:
it makes your copy and uploads the change with it.

### 8c. Put your settings on GitHub (`tracker setup github`)

The set-up goes on with this step after the daily time. To run it on its own
later:

```bash
uv run tracker setup github
```

The run on GitHub cannot read the `.env` file on your computer, so your
settings go into your copy's **secrets** (hidden in every log) and
**variables** (the harmless ones, such as your time zone).

**Your private copy comes first.** The settings are saved into your own private
copy on GitHub, so the set-up first checks that this folder is linked to one.
Only a **private** repository that **you administer** counts as your copy: a
folder still linked to the public Threadline project, or to someone else's
copy, is not, and nothing is saved there. (Without `gh` the set-up can only see
that the folder is linked to GitHub, not whose copy it is.) If it is not
linked to your copy, it says so and, when the GitHub command-line tool `gh` is
installed and signed in (`gh auth login`), offers to create it for you: answer
**y**, then press Return to accept the name `threadline` or type another. It
creates a **private** copy and uploads this folder to it. Without `gh`, it
explains the **Use this template → Private** steps from part 1 and stops; run
`uv run tracker setup github` again from the new copy's `backend` folder.

**The Claude key.** GitHub also needs a key that lets it use your Claude
subscription. The set-up asks for it. Open a second Terminal window (on a Mac:
⌘ + N) and run:

```bash
claude setup-token
```

Sign in in the browser that opens, then go back to that second Terminal window:
it prints a long key that starts with `sk-ant-` and lasts one year. Copy all of
it and paste it into the set-up in the first window when asked (nothing shows
while you paste). The set-up hands it straight to GitHub; it is never saved on
your computer, not even in `.env`. Anyone with this key can use your Claude
subscription, so never paste it anywhere else.

**What the set-up does for you:**

- If the GitHub command-line tool `gh` is installed and signed in
  (`gh auth login`), it offers to save every secret and variable for you, and
  names each one as it goes, never its value.
- Otherwise it prints the **names** to add, opens the page
  (**Settings → Secrets and variables → Actions**), and puts each value on your
  clipboard in turn. On the **Secrets** tab, click **New repository secret**
  for each name in the secrets list; on the **Variables** tab, click **New
  repository variable** for each name in the variables list.

When it saves, the set-up lists every secret and every variable it sets, by
name. The **secrets** include the Claude key, your Supabase keys, the
encryption key, your own addresses (`OWNER_EMAIL_ADDRESSES`), and, when you
have set them, `IMAP_USERNAME`, `DASHBOARD_BASE_URL`, `OWNER_DISPLAY_NAME` and
the LinkedIn values. The **variables** are the harmless settings, such as
`OWNER_TIME_ZONE`, `MAIL_SOURCES` and `IMAP_PROVIDER`.

If you emptied a setting on your computer (for example you removed
`OWNER_DISPLAY_NAME` from `.env`) and GitHub still holds it, the set-up then
lists each one by name and asks once whether to delete them on GitHub, so the
daily run stops using the old values. Answer **y** (or press Return) and it
deletes them and names each one; answer **n** and they stay. This only happens
when `gh` saves the settings for you; by hand, delete them yourself on the
same page.

**✅ Check:** the set-up's list names every secret and variable it set,
including `IMAP_USERNAME`, `DASHBOARD_BASE_URL` and `OWNER_DISPLAY_NAME`
(secrets) and `OWNER_TIME_ZONE` (a variable) if you gave them a value. On
GitHub, **Settings → Secrets and variables → Actions** shows at least
`CLAUDE_CODE_OAUTH_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_ANON_KEY`, `TOKEN_ENCRYPTION_KEY` and `OWNER_EMAIL_ADDRESSES` on the
Secrets tab.

**If not:** add the missing ones by hand on that page, with the exact names.
A name with a typo is ignored. If the set-up stopped with `there is no private
copy on GitHub yet`, make the copy (see above), then run
`uv run tracker setup github` again.

### 8d. Start the first run by hand

1. On GitHub, open **Actions → Threadline run**.
2. Click **Run workflow**, keep **mode: daily**, and click the green **Run
   workflow** button.

**✅ Check:** after a few seconds a new run appears with a yellow dot, and after
about five to ten minutes it has a green tick.

**If not:**

- *Green tick after a few seconds, nothing sent:* a required secret is
  missing. Open the run; a note at the top names the missing secrets. Go back
  to 8c.
- *Red cross:* open the run, click **Threadline**, and open the step with the
  red cross. **Run the recipe with Claude** failing usually means the Claude
  key is wrong or expired: run `claude setup-token` again and replace the
  `CLAUDE_CODE_OAUTH_TOKEN` secret.
- *A run stopped half-way (cancelled, or GitHub stopped it):* nothing to clean
  up. The dashboard's **Daily runs** page shows it as **Running** for a while;
  when the next run starts (at least three hours later), it is closed as
  **Did not work**, with the step where it stopped marked "The run stopped
  here and never finished", and the next morning summary mentions it once.

### 8e. See the log, and the e-mail

Open the finished run and click **Threadline**, then **Run the recipe with
Claude**: the log ends with Claude's short report of the run, in plain
English. It never contains the text of your messages.

**✅ Check:** within about ten minutes of the start, the summary e-mail is in
your inbox, sent from your own mailbox, and the dashboard's **Daily runs** page
shows the run as **Worked** or **Partly worked**.

**If not:** a green tick only means the job ran, not that every part worked.
Read Claude's report at the end of the log, then run `uv run tracker doctor` on
your computer: its **Summary e-mail** line checks that your mailbox accepts the
app password for sending, without sending anything.

From now on the run starts by itself every day at the time you chose. The
dashboard's **Refresh now** button starts the same workflow in **refresh**
mode: it reads only what is new and sends no e-mail. Part 8f switches it on.

### 8f. Switch on Refresh now (`tracker setup refresh`)

The set-up reaches this step right after 8c, so you will meet it before the
first run of 8d. To run it on its own later:

```bash
uv run tracker setup refresh
```

It puts a small helper called `refresh-now` into your Supabase project, so the
button can start an extra update. You install nothing: the set-up does it
through Supabase's and GitHub's websites. It needs two keys, each pasted once
(nothing shows while you paste) and never saved on your computer.

**Before you start:** the dashboard is published (part 7a) and your private
copy is on GitHub (part 8c). If not, the set-up says which part to do first.
As in 8c, only a private repository you administer counts as your copy: if
this folder still points at the public template, the set-up says
`This folder is not linked to your own private copy on GitHub yet` and stops
before anything is made. Without the GitHub command-line tool it cannot check
this, so it names the repository it will use and asks you to confirm it.

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

**2. The Supabase key.** Supabase's **Access Tokens** page opens. Click
**Generate new token**, name it `Threadline refresh now`, and:

1. limit it to this project (the set-up shows its identifier) and choose the
   shortest expiry offered, for example 7 days: it is only used now;
2. under the permissions, give **Edge Functions** and **Edge Function
   Secrets** read and write access, and nothing else;
3. click **Generate token**, copy it (it starts with `sbp_`), and paste it into
   the set-up.

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
- *`Supabase did not accept the access token`:* make the Supabase key again
  with both permissions ticked and this project chosen.
- *`The workflow is switched off on GitHub`:* open the link the set-up shows
  and click **Enable workflow**.
- *The dashboard still says "not switched on yet":* close the dashboard tab and
  open it again (it remembers that answer until the tab is closed).
- *`your database does not have the on-time morning start yet`:* run
  `uv run tracker setup database`, then `uv run tracker setup refresh` again.
- Anything else: the manual way in [`docs/refresh-now.md`](refresh-now.md)
  does the same by hand.

---

## 9. The final check

On your computer:

```bash
uv run tracker doctor
```

**✅ Check:** every line starts with `ok` (optional parts may say `skipped`),
and the last line says `Everything Threadline needs is working.`

**If not:** fix the lines marked `PROBLEM` from top to bottom. Each one ends
with the command that repairs it, usually `uv run tracker setup <step>`.

You are done. From now on, [`docs/operations.md`](operations.md) is the page to
keep: what happens every morning, and what to do when the summary asks for
something.

---

## Alternative: the daily run in a Claude cloud routine

Use this instead of part 8 only if GitHub does not suit you, most often
because you read **only Outlook**, whose mail programs cannot send with an app
password. A Claude cloud routine sends the summary through Claude's Gmail
connector, so you also need a Google account with Gmail. Do not run both
routes: you would get two e-mails.

Set `SUMMARY_DELIVERY=gmail_connector` in `.env` if you also read a Gmail or
other IMAP mailbox: a Claude cloud session can most likely reach only web
addresses, not the mail ports that sending by SMTP needs.

This part is done on <https://claude.ai/code> and cannot be automated from
your computer.

### A1. Let Claude open your copy of Threadline

Go to <https://github.com/apps/claude>, install the **Claude** GitHub app, and
give it access to your Threadline copy only.

**✅ Check:** at <https://claude.ai/code> your Threadline copy appears in the list
of repositories.

**If not:** open the Claude app's settings on GitHub and add the repository.

### A2. Create the cloud environment (`tracker setup cloud`)

Answer **yes** when the set-up asks whether to set up the Claude cloud
routine instead.

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
   `NAME=`, go back to Terminal and press Return to get the value onto the
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

### A3. Connect Gmail

In Claude, open **Customize → Connectors**, click **+**, choose **Gmail** and
click **Connect**.

**✅ Check:** Gmail is listed as connected.

**If not:** disconnect it and connect it again, making sure you allow sending.

### A4. Create the routine

1. Go to <https://claude.ai/code/routines> and click **New routine**.
2. **Name:** for example `Threadline daily run`.
3. **Repository:** your Threadline copy. **Environment:** the one from A2.
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
