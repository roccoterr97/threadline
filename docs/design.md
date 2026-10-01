# Design — Threadline

> This is the original design document: the plan Threadline was built from,
> written in plain language on purpose because its first owner was not a
> developer. It is kept as a record of why the tool is shaped the way it is.
> Where the finished tool differs from the plan, a note says so. For how the
> code works today, read [`architecture.md`](./architecture.md).

## Problem

The owner is looking for a job in a startup and runs two outreach motions at
once:

1. **Direct** — founders, executives and employees of startups.
2. **Network** — venture-capital people (talent/people officers, investment
   team) and friends who can make introductions.

The conversations are spread over LinkedIn messages and a personal
Outlook.com / Hotmail mailbox. Nothing shows, in one place, who the owner is
talking to, where each conversation stands, who owes whom a reply, and which
follow-ups are overdue. Keeping a spreadsheet by hand does not last. Research
at the time found no ready-made product that covers this (the closest options
cost money every month, break LinkedIn's rules, or do not read a personal
Microsoft mailbox).

## What We're Building

A private web dashboard that fills itself in. Once a day the tool collects the
new LinkedIn messages and mailbox emails, throws away the noise, groups what is
left into one conversation per person, and lets AI work out for each person:
the status, who is waiting on whom, the next action and when it is due. The
owner opens the dashboard on a phone or laptop and sees what to do today. The tool
only reads and tracks — it never writes or sends messages to anyone else.

Main screens:

- **Home** — four counters (actions for me · waiting on them · overdue
  follow-ups · active conversations) above the people table.
- **People table** — one row per person: organisation, type (startup / VC /
  network), last contact, status, waiting on, next action, due date, signal.
- **Person page** — AI summary plus the full timeline across LinkedIn and email.
- **To review** — items the AI is unsure about, with Yes / No buttons. Answers
  are remembered.
- **Morning email** — a short daily summary sent to the owner: due today,
  overdue, who replied.

## Target Users

One user: the owner. Not technical. Uses a Mac and a phone. Everything the
owner must do in person (setup, yearly key renewal) needs click-by-click
instructions. All
wording in the dashboard is plain English.

## Scope

### In scope (MVP = Milestones 1–4)

- Read LinkedIn messages through LinkedIn's official Member Data Portability
  channel (EU members).
- Read the personal Outlook.com / Hotmail mailbox, read-only.
- First run covers the last 30 days; afterwards one update per day.
- Noise filter: simple rules first, AI only for the unclear cases.
- Group messages into conversations and match the same person across LinkedIn
  and email.
- AI assessment per person: status, waiting on, next action, due date, short
  summary, signal (positive / neutral / cold).
- "To review" list with Yes / No, and manual corrections that the AI respects
  on later runs.
- Private dashboard with login, usable on phone and laptop.
- Daily morning summary email to the owner.
- Reminder email before the LinkedIn key expires (about every 12 months).

### Deferred (after the MVP)

- Views by company and by opportunity (one person → several companies, several
  people → one opportunity). The data model allows for it from day one.
- More than one update per day (the frequency is a single setting).
- Calendar events, search questions in plain English ("who am I waiting for?").
  *Since built:* the Outlook calendar is read as a third source, and the
  dashboard shows the meetings coming up. Plain-English questions are not
  built.
- Notes typed by hand on a person (calls, meetings in person).
- A small "refresh now" button on the dashboard for a manual update between
  daily runs (to decide later).
- Additional sources such as Gmail (to decide later).

### Out of scope

- Writing, suggesting or sending replies. Track only, permanently.
- Any unofficial LinkedIn reading (scraping, browser automation, paid
  automation tools). The LinkedIn account must never be put at risk.
- Instant / real-time updates.
- Paid AI APIs. All AI runs on the Claude subscription.
- Other chat channels (WhatsApp, phone) and other users.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React + TypeScript, built as a static site | Matches repo standards; static sites are free to host and have nothing to keep running |
| Backend | No always-on server. Python collection/processing jobs run inside one daily scheduled Claude Code cloud session | Included in a Claude subscription, works with the laptop off, no servers to maintain |
| AI | Claude, inside that same daily cloud session (rules first, AI for unclear items) | Satisfies "subscription, not API" |
| Database | Supabase (hosted Postgres), free tier | The dashboard must save Yes/No answers and corrections, so plain files are not enough; also a safe writable place for the rotating Microsoft sign-in key |
| Auth | Supabase login by email link; the one allowed login is recorded in the `app_owner` table, and database rules restrict every table to that user | No password to manage; data unreadable without login |
| Hosting | Free static hosting (Cloudflare Pages or Vercel) deployed from the private GitHub repo | Free, automatic deploys |
| Email reading | Microsoft Graph, read-only permission, personal-account sign-in; rotating key stored encrypted in the database | The official Claude connector rejects personal Microsoft accounts |
| LinkedIn reading | LinkedIn Member Data Portability API (official, free, EU) | Zero account risk; returns full history with same-day freshness |
| Observability | A run-log table (one row per daily run: counts, errors) shown in the dashboard, plus a failure notice in the morning email | The owner must be able to see "did it run today?" without reading logs |

**Fallback if the cloud session cannot reach the mailbox reliably:** the same
jobs run from a daily scheduled task on the owner's Mac. Nothing else changes.

## Constraints

- AI must run on a Claude subscription. A paid API is a last resort and
  needs the owner's explicit yes.
- Budget: no new monthly costs. Free tiers only.
- LinkedIn account safety is absolute: official channel only.
- Mailbox access is read-only. The tool never sends on the owner's behalf
  except the summary email to the owner.
- Secrets (LinkedIn key, Microsoft key, database key) never enter the GitHub
  repo or the chat. Locally they live in `.env`; in the cloud, in the
  scheduled session's secret settings.
- Privacy: the first run looks at the last 30 days; store message text only
  for job-search conversations; for noise store just an ID and the decision.
  *Confirmed by the owner:* when a conversation had activity in the
  last 30 days, the whole thread is kept (including older messages), because a
  status cannot be judged from half a conversation.
- Must keep working with the laptop off (goal; Mac fallback accepted for the
  email part only).
- Scheduled cloud sessions run at most hourly; one run per day is the design
  point.
- Build with parallel agents where tasks are independent, never at the cost of
  quality.

## Data Model (sketch)

- **Person** — name, LinkedIn profile link, email addresses, type (startup /
  VC / network), organisation.
- **Organisation** — name, kind (startup / VC fund / other).
- **Opportunity** — a role or lead at an organisation; linked to one or more
  people (used fully after the MVP).
- **Conversation** — one thread on one channel (LinkedIn, email or, since
  built, calendar), linked to a person.
- **Message** — channel, date, direction (from me / to me), text, link to its
  conversation. Unique per source ID so re-reading never duplicates.
- **Person state** — the AI's current view: status, waiting on (me / them /
  nobody), next action, due date, summary, signal, confidence; plus any manual
  override by the owner, which always wins.
- **Review item** — a question for the owner (relevant or not? same person?)
  and the answer given.
- **Run log** — when each daily run happened, what it found, any errors.

Status is a closed list (the final wording is set in
`docs/assessment-guide.md`): contacted – no reply yet · in conversation ·
meeting planned · in process · gone quiet · closed.

## Non-Functional Requirements

| Concern | Target |
|---------|--------|
| Performance | Daily run finishes in under 15 minutes; dashboard opens in under 3 seconds on a phone |
| Availability | One successful run per day; a missed day is caught up automatically on the next run; failures are visible in the dashboard and the morning email |
| Security / privacy | Login required; every database table locked to the single user; secrets outside the repo; read-only mailbox access; private GitHub repo |
| Accessibility | Readable on a phone; colour is never the only signal (text labels next to coloured dots); keyboard-usable |

## Milestones

### Milestone 1: Collect both sources

**Build:** Set up the database. Collector for LinkedIn (official channel, last
30 days, grouped by conversation). Collector for the mailbox (read-only), trying
the cloud route first and the Mac route as fallback. Match each conversation to
a person, merging the same person across LinkedIn and email where the evidence
is clear. No AI yet.

**Done when:** Running the collectors fills the database with the last 30 days
from both sources, running them twice creates no duplicates, and a simple list
shows every person with their message count and last contact date. The
cloud-or-Mac decision for the mailbox is made and recorded.

---

### Milestone 2: The AI brain

**Build:** Noise filter (rules first, Claude for unclear cases). For every
relevant person, Claude produces status, waiting on, next action, due date,
summary and signal. Unsure items go to the review list. The owner's answers and
manual corrections are stored and respected on later runs. Runs on the Claude
subscription.

**Done when:** On the owner's real last-30-days data, the owner checks 20
people at random and at least 17 have the right status and "waiting on"; newsletters and
notifications are not in the people list; a correction made by hand survives
the next run.

---

### Milestone 3: Online dashboard

**Build:** Private web page with login: four counters, people table (sort and
filter by type, status, waiting on), person page with summary and timeline,
review list with Yes / No, "last updated" indicator from the run log.

**Done when:** The owner logs in on a phone and a laptop, sees real data,
answers a review question, changes a status by hand, and sees both saved.
Nobody else can open the data without the owner's login.

---

### Milestone 4: Daily run + morning email (MVP complete)

**Build:** One scheduled daily run that collects, filters, assesses and saves
(cloud session; Mac task if Milestone 1 chose the fallback). Morning summary
email. Failure notice. LinkedIn-key expiry reminder.

**Done when:** For five days in a row, with no action from the owner, the dashboard
is updated each morning and the summary email arrives; a deliberately broken
run produces a visible failure notice instead of silence.

---

### Milestone 5: After the MVP (optional extras)

**Build:** Company and opportunity views; adjustable update frequency (for
example three times a day); hand-typed notes on a person; plain-English
questions over the data.

**Done when:** Each extra is planned and accepted on its own; none is required
for the MVP.

---

## Success Criteria

- The owner does no manual data entry: both channels fill Threadline by
  themselves.
- Each morning the owner knows in under two minutes what to do today.
- No follow-up is forgotten: every person the owner is waiting on has a
  follow-up date.
- The tool keeps working for weeks with the laptop off (or, under the fallback,
  with the Mac opened once a day).
- Zero new monthly cost, zero paid AI API, zero risk to the LinkedIn account.

## Settled by tests before building

- **Microsoft sign-in (personal account):** works with a one-time code sign-in
  using the public app ID of the open-source ms-365-mcp-server, read-only
  permission (`Mail.Read`) only. No Microsoft developer account needed. The
  long-lived key renews without the owner and changes on every renewal, so each
  run must save the new key (database, encrypted). Risk to accept: the app ID
  belongs to a third party; if it is ever withdrawn, the owner registers a
  free app of their own and signs in again.
- **Cloud route:** the default cloud environment blocks Microsoft, LinkedIn and
  the database. The owner creates a dedicated cloud environment (a suggested
  name is "Threadline") with a custom allowed-sites list (`graph.microsoft.com`,
  `login.microsoftonline.com`, `api.linkedin.com`, `*.supabase.co`). Re-test
  from that environment: Microsoft mailbox service and sign-in reachable,
  LinkedIn reachable, other sites still blocked as intended. The daily run must
  use this environment.
- **Volumes:** most email in a personal mailbox is noise, so the rules-first
  filter matters; the owner's own sent messages are a strong signal of which
  conversations are real.
- **Morning email:** sent through the Gmail connector already linked to the
  Claude account (available to cloud runs automatically), to the owner's own
  address (for example `you@example.com`). The mailbox collector ignores these
  summary emails. No new service, no send rights on the mailbox.
- **LinkedIn sponsored messages / InMail adverts:** noise, unless the owner replied
  positively — then the conversation is relevant (owner's rule).
- **No silent fallback:** if the cloud route has problems (key renewal fails,
  Microsoft blocks the sign-in, a run is missed), the tool flags it clearly in
  the dashboard and the morning email. Switching to the Mac route is the owner's
  decision, never automatic.
- **Claude plan limits for one daily run:** treated as fine by the owner;
  watch the run log for the first week.

## Open questions at the time

Both were answered by building and running the tool; they are kept for the
record.

- Database reachability from the cloud: the database is **Supabase, free plan,
  EU Central (Frankfurt)** and its address will be
  `https://<project-id>.supabase.co`. The cloud test used a made-up address of
  that shape, so it proved "not blocked" rather than "works". Re-check with the
  real address once the project exists.
- Reliability over time of the cloud route (key renewal every day, Microsoft
  not flagging the cloud sign-in as unusual) can only be proven by running it
  for several days — observed during Milestone 4. Mac fallback stays available.
