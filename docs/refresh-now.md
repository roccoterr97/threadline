# Switching on "Refresh now"

Threadline updates itself once a day, at the time you chose. The **Refresh now**
button at the top of the dashboard starts one extra, quick update whenever you
want one: it reads new messages and works out where each person stands. It does
**not** send the morning e-mail.

Until you switch it on, the button tells you that it is not switched on yet.
Nothing else changes.

## How it works, in one paragraph

The button cannot hold a secret key, because anyone can read what a web page
contains. So it asks a small helper that lives in your Supabase project (an
"Edge Function" called `refresh-now`). The helper checks that it is really you,
refuses if an update is already running or one was started less than 10
minutes ago, and then asks the service that runs your updates to start one.
That service is either:

- **GitHub** (the main way): the same GitHub workflow that runs your daily
  update, started once more; or
- **Claude**: your Claude cloud routine, if that is how you run the daily
  update.

The key for GitHub or Claude is stored only inside Supabase, never in the
dashboard.

## What it costs

| Service | What one refresh uses | Cost on the free plan |
|---------|-----------------------|-----------------------|
| Supabase | one call to the helper | free: the free plan includes 500,000 calls a month |
| GitHub | a few minutes of GitHub Actions time | comes out of the same free monthly minutes as your daily run |
| Claude (only if you use the routine) | one routine run | counts toward your Claude plan's usage and its daily limit on routine runs (shown at claude.ai/code/routines) |

A refresh is quick, but it is a full run of the reading and sorting steps. If
you press it many times a day on GitHub, keep an eye on your monthly minutes
(**GitHub → Settings → Billing and plans**).

---

## The quick way: one command

If your daily update runs on **GitHub** (the main way), switch it on with:

```bash
uv run tracker setup refresh
```

in Terminal, in your Threadline folder. You install nothing else: the set-up
opens a GitHub page and a Supabase page, you make one key on each and paste
it, and it does what steps 2A, 3 and 4 below do by hand. [Part 8f of the
set-up guide](./setup-your-accounts.md) walks through it, with what to tick on
each page. If you set Threadline up before Refresh now existed, run
`uv run tracker setup database` first (step 1).

**✅ Check:** the set-up ends with `Refresh now is switched on`, and
`uv run tracker doctor` shows `ok` on its **Refresh now** line.

**If not:** follow the line the set-up printed. If it keeps failing, or your
daily update runs as a **Claude routine**, use the manual way below.

---

## The manual way

Use this when the quick way is not possible, or for a Claude routine. After
every step there are two lines:

- **✅ Check:** what you should see if the step worked.
- **If not:** what to do if you see something else.

> **Websites change.** Button names below were right when this guide was
> written. If a page looks slightly different, look for a button with a similar
> name.

---

## 1. Update the database

Refresh now needs one small addition to your database: a list of when the
button was last used, so it can say "wait a few minutes".

**What you do:** in Terminal, in your Threadline folder, run:

```bash
uv run tracker setup database
```

and answer as in the main set-up guide ([step 3c](./setup-your-accounts.md)).

**✅ Check:** you see `Applied 0013_refresh_requests` (or, if it was already
there, `The database structure is in place.`).

**If not:** open **Supabase → SQL Editor → New query**, paste the whole of
`supabase/migrations/0013_refresh_requests.sql`, click **Run**, and wait for
`Success. No rows returned`.

---

## 2. Make the key the helper will use

Do **either** 2A (GitHub, the main way) **or** 2B (Claude routine). Use the
one that runs your daily update.

### 2A. GitHub: a key that can only start your workflow

This key can start workflows in **your copy of Threadline only**, and nothing
else in your GitHub account.

1. Sign in to <https://github.com>. Click your picture (top right) →
   **Settings**.
2. At the bottom of the left menu, click **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** →
   **Generate new token**.
3. **Token name:** `Threadline refresh now`.
4. **Expiration:** pick a date, for example one year from today. Put that date
   in your calendar: the button stops working on that day until you renew the
   key (see [Renew the key](#renew-the-key)).
5. **Repository access:** choose **Only select repositories**, then pick your
   copy of Threadline (for example `your-name/threadline`).
6. **Permissions → Repository permissions → Actions:** choose
   **Read and write**. Leave everything else as it is (GitHub adds
   "Metadata: Read-only" by itself; that is expected).
7. Click **Generate token**, then copy the token that starts with
   `github_pat_`. GitHub shows it **only once**; keep the page open until
   step 3.

**✅ Check:** the token list shows `Threadline refresh now` with one
repository and an expiry date.

**If not:** if you see "Classic" tokens instead, go back and pick
**Fine-grained tokens**. If your copy of Threadline is not in the list, it may
belong to an organisation: choose that organisation as the **Resource owner**
first.

Also write down two names you will need in step 3:

- your repository, as `owner/name` (the part after `github.com/` in its
  address, for example `your-name/threadline`);
- the branch your workflow runs on — almost always `main`.

### 2B. Claude routine: a key that can only start your routine

1. Go to <https://claude.ai/code/routines> and open the routine that runs your
   daily update.
2. Click **Edit** → **Add another trigger** → **API** →
   **Generate token**.
3. Copy **both** the address shown (it ends in `/fire`) and the token (it
   starts with `sk-ant-oat01-`). The token is shown **only once**.
4. Make sure the routine's instructions say what to do when it is started
   with the text `mode: refresh`: read new messages and work out where each
   person stands, and **do not send the e-mail**. (Claude treats the text
   that comes with the button as information, so the routine's own
   instructions must say to act on it.)

**✅ Check:** the routine shows an **API** trigger.

**If not:** the API trigger can only be added on the claude.ai website, not in
the app or the terminal. Routines need a paid Claude plan with Claude Code on
the web switched on.

> A routine can be started at most 30 times an hour, and your account has a
> daily limit on routine runs (shown on the routines page). A refresh started
> from the button most likely counts toward that limit. If you run into it,
> switch to GitHub (2A).

---

## 3. Give the helper its settings

The helper reads its settings from **Supabase → Edge Functions → Secrets**
(the page may be called **Edge Function Secrets**). Add each line below with
**Add new secret** (name on the left, value on the right), then click
**Save**. You need to be the owner or an administrator of the Supabase
project.

**For GitHub (2A):**

| Name | Value |
|------|-------|
| `REFRESH_TARGET` | `github` |
| `GITHUB_TOKEN_REFRESH` | the `github_pat_…` token from step 2A |
| `GITHUB_REPOSITORY` | your repository, e.g. `your-name/threadline` |
| `GITHUB_REF` | the branch, usually `main` (you can leave this out for `main`) |
| `DASHBOARD_ORIGIN` | your dashboard's address, e.g. `https://threadline-you.vercel.app` |

**For the Claude routine (2B):**

| Name | Value |
|------|-------|
| `REFRESH_TARGET` | `claude_routine` |
| `ROUTINE_FIRE_URL` | the address ending in `/fire` from step 2B |
| `ROUTINE_TOKEN` | the `sk-ant-oat01-…` token from step 2B |
| `DASHBOARD_ORIGIN` | your dashboard's address, e.g. `https://threadline-you.vercel.app` |

`DASHBOARD_ORIGIN` is the address in your browser's address bar when the
dashboard is open, **without** anything after the name (no `/` at the end, no
`/runs`). The helper refuses requests from any other web page.

**✅ Check:** the secrets list shows every name above. Supabase shows only a
short fingerprint of each value, never the value itself — that is expected.

**If not:** a name must be typed exactly as above, in capitals. If Supabase
refuses to save, check that your role in the project is **Owner** or
**Administrator**.

You can now close the GitHub or Claude page with the token: it is saved.

---

## 4. Put the helper in place

Choose **one** of the two ways.

### 4A. In the Supabase website (no terminal)

1. Open **Supabase → Edge Functions** → **Deploy a new function** →
   **Via Editor**.
2. Name the function exactly `refresh-now`.
3. The editor opens with an example file called `index.ts`. Delete its
   contents and paste the whole of
   `supabase/functions/refresh-now/index.ts` from your copy of Threadline.
4. Add a second file with the editor's **add file** button (usually a `+`
   next to the file list), name it exactly `refresh.ts`, and paste the whole
   of `supabase/functions/refresh-now/refresh.ts`.
5. Click **Deploy function** and wait 10 to 30 seconds.
6. Open the function's **Details** (or **Settings**) and switch
   **Enforce JWT verification** (sometimes called **Verify JWT**) **off**.
   The helper checks the sign-in itself and only answers the dashboard's
   owner; with Supabase's own check on, the browser's first "may I?" request,
   which carries no sign-in, is turned away and the button cannot reach it.

**✅ Check:** `refresh-now` appears in the Edge Functions list with a green
status.

**If not:** if the editor has no way to add a second file, use 4B instead.
If the deploy fails with a message about `refresh.ts`, check that the second
file's name is exactly `refresh.ts`.

> The website editor keeps no history. That is fine here: the files in your
> copy of Threadline are the originals, and you can paste them again at any
> time.

### 4B. With the terminal

In Terminal, in your Threadline folder:

```bash
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase functions deploy refresh-now --no-verify-jwt
```

`<your-project-ref>` is the part before `.supabase.co` in your Supabase
address. `--no-verify-jwt` is needed and safe: the helper checks the sign-in
itself (see 4A, point 6).

**✅ Check:** the last command ends with `Deployed Functions on project …:
refresh-now`.

**If not:** if `login` opens a browser page, finish signing in there and run
the command again. If `link` asks for the database password, it is the one
you chose when you created the Supabase project.

---

## 5. Try it

1. Open your dashboard and sign in.
2. Click **Refresh now** (on a phone: **Refresh**, at the top next to
   **Sign out**).

**✅ Check:** the line under the header says "Refreshing… new messages will
appear in a few minutes." Within about 15 minutes it changes to "Refresh
finished…", and **Daily runs** shows a new run at the top.

**If not:** the line under the header says what went wrong. The table below
says what to do.

| The dashboard says | What to do |
|--------------------|------------|
| "not switched on yet" | The helper is not deployed, or not under the name `refresh-now`: run `uv run tracker setup refresh`, or do step 4 again. Then close the dashboard tab and open it again (it remembers the answer until the tab is closed). |
| "only half set up" | A setting in step 3 is missing or mistyped, or step 1 was skipped. Check each name and value. `GITHUB_REPOSITORY` must look like `owner/name`; `ROUTINE_FIRE_URL` must start with `https://api.anthropic.com/` and end with `/fire`. |
| "You seem to be offline" | Check your internet connection, then try again. |
| "does not recognise this web address" | `DASHBOARD_ORIGIN` does not match the address in your browser. Fix it in step 3. |
| "turned down the key" | The key has expired or was deleted: see [Renew the key](#renew-the-key). |
| "could not find what Refresh now should start" | GitHub: check `GITHUB_REPOSITORY`, and that the workflow file `threadline-run.yml` exists on the branch in `GITHUB_REF`. Claude: check `ROUTINE_FIRE_URL`. |
| "turned the request down" | GitHub: the workflow is switched off (**Actions** tab of your repository → the workflow → **Enable workflow**), or the branch in `GITHUB_REF` does not exist. Claude: the routine is paused. |
| "too many requests in the last hour" | Wait an hour. |
| "already running" / "You can start the next one in …" | Nothing is wrong: wait, as it says. |
| "Only the owner of this dashboard can start a refresh" | You are signed in with an address that is not the owner's. |

---

## Renew the key

GitHub keys expire on the date you chose in step 2A; a Claude routine key
stays valid until you make a new one. When the dashboard says the key was
turned down:

With GitHub, the quickest way is to run `uv run tracker setup refresh` again:
it opens the page for a new key and saves it. By hand:

1. Make a new key: repeat step **2A** (GitHub) or step **2B**, points 1–3
   (Claude; making a new routine key cancels the old one).
2. In **Supabase → Edge Functions → Secrets**, change the value of
   `GITHUB_TOKEN_REFRESH` (GitHub) or `ROUTINE_TOKEN` (Claude) to the new key,
   and click **Save**. There is no need to deploy the helper again.
3. On GitHub, delete the old key from the **Fine-grained tokens** list.

**✅ Check:** **Refresh now** says "Refreshing…" again.

**If not:** check that you pasted the whole key, with nothing before or after
it, and saved. Then try once more.

---

## Switching it off

Delete the `refresh-now` function in **Supabase → Edge Functions**, and delete
the key on GitHub (**Fine-grained tokens**) or on the routine (remove the API
trigger). The button then says that Refresh now is not switched on.
