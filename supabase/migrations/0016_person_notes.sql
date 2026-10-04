-- Threadline — notes the owner types by hand on a person.
--
-- "Met at the Lyon fair, prefers calls after 4pm": things no message says and
-- the owner wants to find again on that person's page. A person can have
-- several notes; each is plain text with the moment it was written and the
-- moment its text last changed.
--
-- The notes are for the dashboard only. The Python jobs never read a note's
-- text: it is not sent to the AI assessment and is not in the summary e-mail.
-- The one thing the jobs do with this table is point a note at the surviving
-- record when two records of one person are joined (`tracker people merge`),
-- so the note is not removed together with the record that goes.
--
-- The signed-in owner may read, add, change the text of and delete notes —
-- nothing else: a note can never be moved to another person or given another
-- date from the dashboard. The public key gets nothing.
--
-- Safe to run twice.

create table if not exists public.person_notes (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references public.people (id) on delete cascade,
  -- At least one visible character (`btrim` would let a note made of line
  -- breaks through), and short: a note, not a document.
  body text not null check (body ~ '\S' and char_length(body) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.person_notes is
  'Notes the owner types by hand on a person, shown on the dashboard only. '
  'Never sent to the AI assessment and never part of the summary e-mail.';
comment on column public.person_notes.body is
  'The note, as plain text. The dashboard holds the same 2000-character limit.';
comment on column public.person_notes.updated_at is
  'When the text last changed. Joining two records of one person moves a note '
  'without changing this.';

-- The dashboard reads one person's notes, newest first.
create index if not exists person_notes_person_created_at_idx
  on public.person_notes (person_id, created_at desc);

-- Only a change of the text counts as a change: when `tracker people merge`
-- points a note at the surviving record, the dashboard must not start saying
-- the owner changed it that day.
drop trigger if exists person_notes_set_updated_at on public.person_notes;
create trigger person_notes_set_updated_at
  before update on public.person_notes
  for each row
  when (old.body is distinct from new.body)
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Access (see 0002): the owner reads, adds, edits the text and deletes; the
-- public key gets nothing.
-- ---------------------------------------------------------------------------

alter table public.person_notes enable row level security;

revoke all on public.person_notes from anon, authenticated;
grant select on public.person_notes to authenticated;
-- A new note names its person and its text; the id and the dates are the
-- database's. An edit can only change the text.
grant insert (person_id, body) on public.person_notes to authenticated;
grant update (body) on public.person_notes to authenticated;
grant delete on public.person_notes to authenticated;
-- Granted explicitly so the Python jobs do not depend on Supabase's defaults.
grant select, insert, update, delete on public.person_notes to service_role;

drop policy if exists "owner reads person_notes" on public.person_notes;
create policy "owner reads person_notes" on public.person_notes
  for select to authenticated using (public.is_app_owner());

drop policy if exists "owner adds person_notes" on public.person_notes;
create policy "owner adds person_notes" on public.person_notes
  for insert to authenticated with check (public.is_app_owner());

drop policy if exists "owner edits person_notes" on public.person_notes;
create policy "owner edits person_notes" on public.person_notes
  for update to authenticated using (public.is_app_owner()) with check (public.is_app_owner());

drop policy if exists "owner removes person_notes" on public.person_notes;
create policy "owner removes person_notes" on public.person_notes
  for delete to authenticated using (public.is_app_owner());
