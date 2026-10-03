# Customising Threadline

Threadline can follow any kind of conversation you keep alive: a job search,
sales, fundraising, freelance work or simply your network. Two things change
between them:

- your **categories** — who someone is to you. "Startup", "Investor" and
  "Network" for a job search; "Prospect", "Customer" and "Supplier" for sales.
  You choose them yourself, on the dashboard or in the terminal.
- the **wording** — what the six stages of a conversation are called ("In a
  hiring process" for a job search, "In a deal" for sales), what counts as
  relevant for you, and a few examples the AI helper reads. This comes from a
  **preset**.

No code is involved in either.

---

## The presets

Five presets ship with Threadline. Each one suggests some categories — you keep
the ones you use, drop the others, and add your own.

| Preset | For | Suggested categories |
|--------|-----|----------------------|
| `job_search` | Looking for a role | Startup, Investor, Network |
| `sales_outreach` | Selling | Prospect, Customer, Partner, Referrer |
| `fundraising` | Raising money | Investor, Angel, Adviser, Introducer |
| `freelance_clients` | Finding and keeping clients | Lead, Client, Past client, Agency |
| `networking` | Keeping in touch | Contact, Mentor, Peer |

There is always one more category, **Not known**, for people who cannot be
placed yet. It is added for you and cannot be changed or removed.

If you choose nothing, Threadline uses `job_search`.

---

## Way 1: on the dashboard (easiest)

1. Open your dashboard and sign in.
2. Open **Settings** in the menu.

   ✅ Check: you should now see a **Categories** section with **Your
   categories**, each with its colour, and **Not known** at the end.

3. **Keep only what you use.** Next to a category you do not need, press
   **Remove**. The dashboard asks you to confirm before it removes anything.

   ✅ Check: after you confirm, it disappears from the list. If some people already had it, it
   moves to **Hidden categories** instead, and those people keep it.

4. **Add a suggestion.** Under **Suggestions**, press the one you want, for
   example **Add Customer**.

   ✅ Check: it appears at the end of your categories, before **Not known**.

5. **Add your own.** Under **Add your own**, fill in a name ("Supplier"), a name
   for a group ("Suppliers"), who belongs there in one sentence ("Companies
   that sell to us") and a colour, then press **Add category**. The sentence matters: the
   AI helper reads it to decide who goes where.

   ✅ Check: "Supplier" appears in your categories with the colour you picked.

6. **Rename, recolour or reorder.** Press **Change** on a category to change its
   name, group name, sentence or colour, then **Save**. Use **Move up** and
   **Move down** to change the order; the dashboard's filters and columns
   follow it.

   ✅ Check: the home page's filter chips show the new names, in the new order.

7. **Wait for the next morning.** The AI helper learns about your changes at
   the start of the next daily run.

   ✅ Check: the next morning, new conversations are sorted into your new
   categories. People you corrected by hand keep what you set.

You can have up to eight categories besides **Not known**. Two categories
cannot have the same name or the same name for a group, whatever the capitals
("customer" and "Customer" count as the same): the page refuses the second one
and says why. A
category that is hidden because people still have it can be brought back with
**Show again**.

---

## Way 2: in the terminal

From the project folder:

```bash
cd backend && uv run tracker profile choose
```

It asks, one question at a time:

1. which preset is closest to what you track — type its number;
2. whether to use all the suggested categories — press Enter for yes. If you
   type `n`, it then asks about each suggestion in turn: press Enter to keep
   it, or type `n` to drop it;
3. whether to add a category of your own — for each one, its name, the name for
   a group, who belongs there, and a colour;
4. whether to save.

✅ Check: it ends with `categories saved: …`, `stage labels saved: 6` and
`guide written: docs/assessment-guide.md`. The dashboard's Settings page now
shows the same categories.

The preset you chose is remembered in your database, so the morning run uses
its wording too. You can run `tracker profile choose` again at any time; it
replaces your categories with the new answers (people keep a category that is
removed — it is hidden, not deleted). If a new category has the name of one
that is hidden, the hidden one gets " (2)" after its name, so the two never
look alike: switching from the job-search list to the fundraising list, for
example, keeps the people you filed as "Investor" under "Investor (2)" next to
the new, empty "Investor". It then says
`renamed so no two categories share a name: vc is now Investor (2)`.

The guided set-up asks the same questions in its categories step, and
`uv run tracker setup categories` runs that step on its own. It saves your
answers in exactly the same way, and ends with
`Saved … categories, 'Not known' included.`

---

## For people who prefer a file

Everything a preset contains — the wording, the six stage labels, the guidance
for the AI and the suggested categories — can be edited in a text file.

1. Copy a preset to `profile/profile.toml`:

   ```bash
   cp profile/presets/sales_outreach.toml profile/profile.toml
   ```

2. Edit it in any text editor. Comments at the top explain each part. Then:

   ```bash
   cd backend && uv run tracker profile check
   ```

   ✅ Check: it prints `profile: … from profile/profile.toml`, your suggested
   categories and the six stage labels. If something is wrong it prints one line
   naming the part at fault, such as
   `categories.2.colour: Input should be 'violet', 'cyan', …`.

3. Put it into effect:

   ```bash
   cd backend && uv run tracker profile apply
   ```

   ✅ Check: it prints `stage labels saved: 6`, `suggestions saved: N` and
   `guide written: docs/assessment-guide.md`.

   This leaves the categories you set on the dashboard alone. To make your
   categories exactly the file's list instead, add `--categories`:
   `uv run tracker profile apply --categories`.

4. **Commit `profile/profile.toml` to your own copy of the project.** The daily
   run happens on GitHub (or in a Claude cloud routine), from your repository;
   a file that only exists on your computer never reaches it.

When `profile/profile.toml` exists, it wins over a preset chosen with
`tracker profile choose`.

### What is in the file

- `[wording]` — `subject` ("your sales outreach"), `relevance_question` (the
  Yes/No question asked when the AI is unsure; it must contain `{name}`), and
  `relevant_means` (what makes someone relevant, in one sentence).
- `[[categories]]` — the suggested categories, each with a `key` (lowercase
  letters, digits and `_`, starting with a letter; `unknown` and `all` are
  reserved), a `label`, a `group_label`, a `colour` and a `description` for the
  AI. At most eight.
- `[stages.<stage>]` — a `label` and a `description` for each of the six
  stages.
- `[guidance]` — `status_examples`, `summary_example` and `relevance`: short
  texts the AI reads. Write `{{stage:in_process}}` instead of a stage's name
  and the text follows when you rename it.
- `[rules]` — collection rules for this kind of work, on top of the general
  ones: systems whose automatic mail is the work itself (hiring systems for a
  job search, booking tools such as Calendly), subject lines that concern your
  own work, and the words that make an entry you typed in your own calendar a
  meeting to track. Leave it out to use only the general rules.

The rest of the AI's guide — waiting-on, due dates, confidence and the safety
rules — is the same for everybody and lives in
`profile/assessment-guide.template.md`.

---

## Colours

`violet`, `cyan`, `orange`, `pink`, `indigo`, `teal`, `olive`, `brown` and
`grey`. Each has a light and a dark version that stays readable on screen. Red,
amber and green are kept for what needs your attention (overdue, your move, a
meeting or a process running), so no category uses them.

## What cannot be changed, and why

The **six stages** — contacted with no reply yet, in conversation, meeting
planned, in process, gone quiet, closed — cannot be added to, removed or
reordered; only their names and descriptions change. Threadline's rules are
built on them: "gone quiet" is set by date after ten days of silence, the
"active" filter means the middle three, and a planned meeting or a running
process is never marked gone quiet just because nobody wrote for a while. A
different set of stages would need different rules, which is a change to the
code.

**Not known** is always there, because every new person starts in it.

Categories, on the other hand, drive no rule at all — which is why you can
change them freely.

## Good to know

- The made-up sample data (`tracker sample load`) uses the job-search
  categories. Load it only while Startup, Investor and Network exist.
- `docs/assessment-guide.md` is rebuilt every morning from your categories and
  your preset or file. Edit those, not the guide.
