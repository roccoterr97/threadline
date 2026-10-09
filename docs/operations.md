# Running it day to day

This page is for you, the owner of Threadline, not for a programmer. It says what happens every
morning, how to tell whether it worked, and what to do about the three or four
things that can go wrong. Nothing here needs you to understand the code.

Keep it open the first week. After that you will only come back to it when the
summary e-mail asks you to.

---

## What happens every morning

At the time you chose (for example 07:07), the **Threadline run** workflow
starts on your private copy on GitHub, with your laptop off, and a Claude
session runs the job on your own Claude subscription. (If you chose the
alternative route, a Claude cloud routine does the same.) In about five to ten
minutes it:

1. opens a new run in the database, so the morning is recorded whatever happens;
2. checks that it can reach the database and read its stored keys;
3. reads your new LinkedIn messages, e-mails and calendar entries, all at the
   same time; if one source is unavailable, the others are still read;
4. reads through what is new and works out, per person, where things stand;
5. builds the summary;
6. e-mails it to your own address (for example `you@example.com`), sent from
   your own mailbox;
7. closes the run with one of three results.

The three results, as the dashboard's **Daily runs** page shows them:

| On the dashboard | Code | What it means |
|------------------|------|---------------|
| **Worked** | `success` | Everything worked. |
| **Partly worked** | `partial` | Something failed or never ran (no summary went out, nothing was collected), the rest worked. The summary opens with "Something needs your attention" and says what to do. |
| **Did not work** | `failed` | Nothing worked. The summary says so. |

**Who starts it on time.** GitHub's own timer often starts the workflow hours
late. With the **on-time morning start** switched on (it comes with
`uv run tracker setup refresh`), your Supabase project looks every 15 minutes
and starts the workflow as soon as your time has passed: usually within a few
minutes, at most about 15. GitHub's own timer stays as a backup: when it
fires later and finds today's run already started, it stops after a few
seconds. If Supabase was down that morning, GitHub's run still goes ahead,
only later. Either way the summary e-mail goes out once a day, never twice.
How it works and what it costs (nothing): [`refresh-now.md`](refresh-now.md),
"The on-time morning start".

**It never silently switches to another way of working.** If LinkedIn or
Microsoft refuses, you are told, and you decide what to do. See
[The Mac route](#the-mac-route-and-when-to-choose-it).

---

## Reading the morning e-mail

The subject always starts with your `SUMMARY_SUBJECT_PREFIX` (`[Threadline]`
unless you changed it), which is also how Threadline
recognises its own summaries and ignores them when it reads your mailbox the
next day. **Never edit that prefix** if you ever forward or re-send one.

The body has the same sections every day, in the same order:

- **Something needs your attention** — only when something failed. One line for
  what did not happen, one line for what to do about it.
- **Do today** — the people waiting on *you*: name, organisation, the next
  action and the date it is due.
- **Overdue follow-ups** — the ones whose date has already passed. Somebody who
  is both waiting on you and overdue appears here only, never twice.
- **Replied since yesterday** — who wrote back since the previous run.
- **To review** — how many yes/no questions are waiting, with a link.
- **LinkedIn key** — only in the seven days before the key expires.

A section with nobody in it says "nobody" rather than disappearing, so you can
tell "nothing to do" from "the e-mail is broken".

If a list is long it is cut after ten people and ends with "and N more on the
dashboard".

**No summary at all one morning is itself a signal**: the run did not start.
Open the dashboard; it shows a banner when the last run is more than 26 hours
old.

---

## Reading the run page

The dashboard's **Daily runs** page lists the last fourteen runs. Each one shows
when it started, how long it took, its result (**Worked**, **Partly worked** or
**Did not work**), and one line per step: LinkedIn, the mailbox, the
reading-through, and the summary e-mail.

A failed step never shows you a technical error. It shows the same plain
sentence the e-mail uses. If you ever see something that looks like computer
output on that page, that is a fault worth reporting.

---

## Renew the LinkedIn key

The key that lets Threadline read your LinkedIn messages lasts until the date
LinkedIn's Token Inspector showed when you made it. Seven days before that date,
every morning summary carries a "LinkedIn key" line with the exact date. It
takes about five minutes.

1. On your computer, open a terminal and type:

   ```bash
   cd ~/threadline/backend
   uv run tracker setup linkedin
   ```

   A key is already saved, so the set-up goes straight to making a new one and
   opens LinkedIn's token page (in LinkedIn's own menu: **Docs and tools →
   OAuth Token Tools → Create token**).
2. On that page, pick your application, tick the permission starting with
   `r_dma_portability`, click **Request access token**, then **Allow**. Copy
   the token and paste it in the terminal. Then read its expiry date in
   LinkedIn's **Token Inspector** and type it. Every click is in the set-up
   guide, part 8a: [stage 3](setup-your-accounts.md#stage-3-of-3-make-the-key)
   and [the expiry date](setup-your-accounts.md#the-expiry-date-and-your-profile-address).
   The set-up checks the key with LinkedIn before it saves anything, and asks
   before replacing the old values.
3. Put the same two values where the daily run reads them, or it keeps using
   the old key: run `uv run tracker setup github`, which saves
   `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_TOKEN_EXPIRES_ON` on GitHub for you
   (press Enter when it asks for the Claude key, to keep the one GitHub has,
   and answer `n` when it offers to start a daily run).
   On the alternative route, update the two in the cloud environment at
   <https://claude.ai/code> instead; `uv run tracker setup cloud` puts each
   value on your clipboard in turn.

**✅ Check:** `uv run tracker doctor` says `ok  LinkedIn key` and shows the new
date.

Until you do this, the daily run keeps working for e-mail and keeps telling you
about LinkedIn every morning. Nothing is lost: once the key works again, the
next run reads everything that arrived meanwhile.

---

## Redo the Microsoft sign-in (about one minute)

The mailbox key renews itself silently. Microsoft occasionally refuses it
anyway — after a password change, a long pause, or a sign-in from an unfamiliar
place. The summary then says "Microsoft refused the saved sign-in".

You have to do this on your computer, because Microsoft shows you a code to
type:

```bash
cd ~/threadline/backend
uv run tracker setup microsoft
```

It opens Microsoft's page and shows a short code. Type the code, approve the
**read-only** mailbox and calendar permissions, and come back to the terminal.
It finishes with "Signed in as" and your address.

Then check it:

```bash
uv run tracker doctor
```

The Microsoft sign-in, Mailbox and Calendar lines should all say `ok`.

The next run on GitHub (or on the alternative route) picks the new key up by
itself: the key lives in the database, not on your laptop.

If Microsoft refuses again within a few days, that is the moment to think about
[the Mac route](#the-mac-route-and-when-to-choose-it).

---

## Renew a mailbox app password (about two minutes)

Gmail, iCloud, Yahoo, Fastmail and other IMAP mailboxes are read with an app
password. The summary says, for example, "Your Gmail could not be read this
morning: Google refused the app password" when it stops working. The usual
reasons:

- you changed your Google or Apple password — that removes every app password;
- you removed the app password yourself, on the provider's page;
- on a work or school account, the administrator switched IMAP or app
  passwords off (only they can switch it back on).

Yahoo keeps app passwords when you change your password, so there it usually
means the app password was removed.

1. Make a new app password, exactly as in part 4 of
   [the set-up guide](setup-your-accounts.md#4b-gmail-or-another-mailbox) for
   your provider.

   **✅ Check:** the provider shows you the new password.

   **If not:** see the "If not" lines of that part — for Gmail, 2-Step
   Verification must still be on.

2. Give it to Threadline:

   ```bash
   cd ~/threadline/backend
   uv run tracker setup mailbox
   ```

   Choose the same provider and the same address, then paste the new password.

   **✅ Check:** it says `Connected. Your inbox has … messages` and then that it
   saved the app password, encrypted.

   **If not:** "refused the app password" means the password was copied wrongly
   or belongs to another account: make another one and try again.

3. Check it:

   ```bash
   uv run tracker doctor
   ```

   **✅ Check:** the `IMAP mailbox` line says `ok`.

There is nothing to change on GitHub or in the cloud: the password lives,
encrypted, in the database, not in the secrets. The next run uses it, both to
read your mail and to send you the summary.
Afterwards, remove the old app password on the provider's page, if it is still
listed.

---

## Renew the Claude key (once a year)

GitHub runs Threadline with the key `claude setup-token` made for you. It lasts
one year. When it expires, the run on GitHub fails with a red cross at the
**Run the recipe with Claude** step, and no summary arrives. Put a reminder in
your calendar for a week before the date you made it.

1. In a terminal, run `claude setup-token`, sign in, and copy the key it
   prints.
2. In the `backend` folder (`cd ~/threadline/backend`), run
   `uv run tracker setup github` and paste the key when asked. It replaces the
   `CLAUDE_CODE_OAUTH_TOKEN` secret and is saved nowhere else. (Without the
   GitHub tool `gh`: on GitHub, open **Settings → Secrets and variables →
   Actions**, click the pencil next to `CLAUDE_CODE_OAUTH_TOKEN`, paste the key
   and save.)
3. When it offers to start a daily run, press Enter for yes. (Without `gh`: on
   GitHub, open **Actions → Threadline run → Run workflow** with mode
   **daily**.)

**✅ Check:** the run gets a green tick and the summary arrives.

The key belongs to your own Claude subscription. Never give it to anybody, and
never paste it anywhere but your own repository's secrets.

---

## Renew the Refresh now key (once a year)

The dashboard's **Refresh now** button starts the workflow with a GitHub key of
its own, which expires on the date you chose when you made it (part 8b of the
[set-up guide](setup-your-accounts.md#8b-refresh-now-tracker-setup-refresh)).
From that day the dashboard says the key was turned down. In a terminal, run:

```bash
cd ~/threadline/backend
uv run tracker setup refresh
```

As in part 8b, it opens GitHub's page for a new key and Supabase's page for a
short-lived token, checks the key, and saves it in your Supabase project.
Nothing changes on your computer. The way by hand is in
[Renew the key](refresh-now.md#renew-the-key).

**✅ Check:** **Refresh now** on the dashboard says "Refreshing…" again.

---

## Pause and resume

**Pause.** On GitHub, open **Actions → Threadline run**, click the **⋯** menu
and choose **Disable workflow**. Nothing is lost while it is off: the next run
reads everything since the last successful one, however long that is. (On the
alternative route: open <https://claude.ai/code/routines> → the daily-run
routine → turn it off.)

**Resume.** Choose **Enable workflow** in the same menu. The first run
afterwards may take longer than usual and its summary may be fuller, because it
catches up on everything it missed.

**Run one morning by hand:** **Actions → Threadline run → Run workflow**, mode
**daily**. Mode **refresh** reads only what is new and sends no e-mail — the
same thing the dashboard's **Refresh now** does. Or, with your laptop on, open
the project in Claude Code and type `/daily-run`: the same recipe, and the
summary goes to the same address.

**Running the morning again the same day** (GitHub's **Re-run jobs**, a second
**Run workflow**, or `/daily-run` by hand) reads and judges everything as
usual, but sends no second e-mail when today's summary already reached you:
the run page shows the e-mail as skipped, naming the run that sent it. If the
earlier e-mail never arrived because sending failed, the re-run sends it. To
get a second copy on purpose, open the project in Claude Code and ask it to
send today's summary again: `tracker summary build` and `tracker summary send`
both accept `--send-again` for exactly this.

**Change the time.** In a terminal, run:

```bash
cd ~/threadline/backend
uv run tracker setup schedule
```

Type the new time; it uses your saved time zone (change that with
`uv run tracker setup timezone`). It shows the change to the workflow file and
offers to commit and push it. It also saves the new time in your database,
which is where the on-time morning start reads it, so the change counts from
the next morning even before you push. GitHub's backup uses the new time once
it is pushed. (On the alternative route, edit the routine's schedule instead.)

**GitHub's free minutes.** A private repository on GitHub's free plan has
2,000 minutes of Actions a month. One run takes about five to ten minutes, so a
month of mornings uses roughly 150 to 300, plus a few for each **Refresh
now**. **Settings → Billing and plans** on your GitHub account shows what is
used.

---

## Publish a newer dashboard

The dashboard on Netlify stays as it was when it was published. To publish it
again, for example after your copy of Threadline was updated, run:

```bash
cd ~/threadline/backend
uv run tracker setup dashboard
```

**✅ Check:** your dashboard's address opens the sign-in page, and after you
sign in it shows your data as before.

**If not:** follow the line the set-up printed, then run the command again.

---

## What a failed run looks like on GitHub

Open **Actions → Threadline run**. Every run is one line:

| What you see | What it means | What to do |
|--------------|---------------|------------|
| Green tick, and the summary arrived | The run worked (the dashboard may still say **Partly worked**: the summary says what needs attention). | Nothing. |
| Green tick after a few seconds, no summary | A required secret is missing, so the run did nothing on purpose. The run page names the missing secrets in a note at the top. | `uv run tracker setup github`. |
| Red cross at **Run the recipe with Claude** | The Claude key was refused or expired, or the session stopped. | [Renew the Claude key](#renew-the-claude-key-once-a-year); if it happens again, read the end of that step's log. |
| Red cross at **Install Threadline** | GitHub could not install the tool, usually a passing outage. | Nothing; the next run tries again. |
| Red cross at **Run the recipe with Claude** after 45 minutes of it | The run took too long and was stopped. | Nothing once; if it repeats, see [When something keeps failing](#when-something-keeps-failing). |
| Green tick after a few seconds, with the note "Today's daily run already started on time" | GitHub's own late start found that the on-time morning start had already started today's run, so it stopped. | Nothing. This is the backup doing its job. |
| A yellow warning at the top: "GitHub could not say whether a refresh is going" | GitHub's own service kept having a hiccup, so the daily run waited as long as a refresh can last and then went ahead. | Nothing. A refresh going at the same time keeps to its own run, so the summary still goes out. |

GitHub e-mails you when a run fails, if your GitHub notification settings allow
it. The log never contains your messages' text or any key.

**The morning run still starts late?** Run `uv run tracker doctor` and read
its **On-time morning start** line:

| It says | What to do |
|---------|------------|
| `ok`, with your time | It is on. If one morning was still late, Supabase was probably down; GitHub's backup ran instead. Nothing to do. |
| `not switched on` | `uv run tracker setup refresh` (and `uv run tracker setup database` first, if it says so). |
| the database and the workflow disagree | `uv run tracker setup schedule`, and press Enter to keep the time. |
| the timer is missing, or the helper answered a status | `uv run tracker setup refresh` again. |

---

## When a setting is missing

The summary says a setting is missing or wrong. This means a value Threadline
needs — the database address, one of its keys — is absent from the place the run
reads it. `uv run tracker doctor` names it.

- If the **GitHub** run says it: run `uv run tracker setup github` on your
  computer. It saves every setting from your `.env` as a secret or a variable
  of your repository, or lists the names so you can add them on
  **Settings → Secrets and variables → Actions**.
- If the **cloud routine** says it (the alternative route): at
  <https://claude.ai/code>, open the
  environment you created for Threadline (the gear next to its name) and check
  every variable is there: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_ANON_KEY`, `TOKEN_ENCRYPTION_KEY`, `OWNER_EMAIL_ADDRESSES`,
  the mailbox settings (`MAIL_SOURCES`, `IMAP_PROVIDER`, `IMAP_USERNAME`),
  `OWNER_LINKEDIN_PROFILE_URL`, `LINKEDIN_ACCESS_TOKEN`,
  `LINKEDIN_TOKEN_EXPIRES_ON` and `DASHBOARD_BASE_URL` (plus
  `MICROSOFT_CLIENT_ID` and `MICROSOFT_TENANT` if you set them). Running
  `uv run tracker setup cloud` on your computer prints the exact list, names
  only, and can copy each value for you. Changes only reach sessions started
  afterwards.
- If a run **on your computer** says it: run `uv run tracker setup`. It asks
  only for what is missing. `.env.example` lists every setting with a comment
  explaining it.

Never paste any of these values into a chat, a document or an e-mail.

---

## When something keeps failing

One bad morning means nothing — services have outages. Use this rule:

| How often | What to do |
|-----------|------------|
| Once | Nothing. The next run catches up. |
| Two mornings in a row | Run `uv run tracker doctor` in the `backend` folder (`cd ~/threadline/backend`). It checks every connection and ends each problem line with the command that fixes it, usually `uv run tracker setup linkedin` or `uv run tracker setup microsoft`. |
| Three mornings in a row, after doing that | Open the project in Claude Code and say: "The daily run has failed three mornings with this message: …" and paste the sentence from the e-mail and the `PROBLEM` lines from the doctor — never a key. |

Two things worth knowing while you wait:

- **Nothing is lost.** Every run reads from the last *successful* one, so a
  missed morning is caught up automatically.
- **Nothing is sent on your behalf, ever.** Threadline only reads. The single
  message it sends is the summary to yourself.

---

## The Mac route, and when to choose it

The daily run lives on GitHub (or, on the alternative route, in a Claude cloud
routine) so your laptop can stay shut. The same recipe can run on the Mac
instead, as a scheduled task, if that route becomes unworkable — for example if
Microsoft keeps refusing sign-ins coming from an unfamiliar address.

**This switch never happens by itself.** Threadline will not quietly change
route and leave you thinking everything is normal: it tells you, every morning,
and waits for you.

Choose it when:

- the Microsoft sign-in has been refused on several mornings in a row even
  though you redid it, **or**
- on the alternative route, the cloud cannot reach your Gmail or other IMAP
  mailbox even though its server is in the allowed domains (IMAP is not web
  traffic; see part 8c of the [set-up guide](setup-your-accounts.md#8c-the-claude-cloud-route-tracker-setup-cloud)), **or**
- the cloud sessions can no longer reach LinkedIn or the database.

What it costs: your Mac must be awake at the scheduled time, and a morning where
it is shut is a morning skipped (caught up the next time it runs).

How to switch: open the project in Claude Code and say "Set up the daily run on
the Mac instead of the cloud". It is a scheduled task that runs the same
`/daily-run` recipe. Disable the GitHub workflow (or turn the cloud routine
off) first, so you do not get two summaries. Before the first unattended run,
open Claude Code once in the project folder and answer yes when it asks
whether to trust this folder: until you do, the project's permissions are
ignored and the unattended run stops at its first question.

---

## The three things Threadline will never do

1. **Never write or send a message to anybody else.** Both sources are read-only
   and the code has no way to reply. The one message it sends is your own
   summary.
2. **Never act on what is inside a message.** The session that runs the day
   never opens message text; only a helper with no tools except reading and
   writing files does, and it may only answer with a verdict file that is
   checked before anything is saved.
3. **Never change route on its own.** Problems are flagged and left to you.
