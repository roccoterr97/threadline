-- Conversation Tracker — a neutral name for the "in a process" stage, and
-- status labels the owner can word (Plan 19).
--
-- The six stages stay fixed: the rules that decide "gone quiet", the active
-- list and the stages a date never overrides are built on them. What changes:
--   * the stage `in_hiring_process` is renamed `in_process`, because a sales
--     deal or a funding round goes through a process too. Rows already holding
--     it follow automatically: Postgres stores an enum value by identity, not
--     by its name. No view, function or trigger names the old value;
--   * `status_labels` holds the words the dashboard shows for each stage
--     ("In a hiring process", "In a deal"…), one row per stage, written by
--     `tracker profile apply`. It is seeded with the words the dashboard used
--     until now, so nothing changes on screen.
--
-- Safe to run twice. Runs inside one transaction: renaming an enum value, unlike
-- adding one, is allowed there.

-- ---------------------------------------------------------------------------
-- in_hiring_process → in_process
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (
    select 1
      from pg_catalog.pg_enum e
      join pg_catalog.pg_type t on t.oid = e.enumtypid
      join pg_catalog.pg_namespace n on n.oid = t.typnamespace
     where n.nspname = 'public'
       and t.typname = 'contact_status'
       and e.enumlabel = 'in_hiring_process'
  ) then
    alter type public.contact_status rename value 'in_hiring_process' to 'in_process';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- The words shown for each stage
-- ---------------------------------------------------------------------------

create table if not exists public.status_labels (
  id uuid primary key default gen_random_uuid(),
  status public.contact_status not null unique,
  label text not null check (btrim(label) <> '' and char_length(label) <= 40),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.status_labels is
  'What the dashboard calls each of the six fixed stages. Written by `tracker '
  'profile apply` with the service key; the dashboard reads it.';

drop trigger if exists status_labels_set_updated_at on public.status_labels;
create trigger status_labels_set_updated_at
  before update on public.status_labels
  for each row execute function public.set_updated_at();

insert into public.status_labels (status, label)
values
  ('contacted_no_reply', 'Contacted, no reply yet'),
  ('in_conversation', 'In conversation'),
  ('meeting_planned', 'Meeting planned'),
  ('in_process', 'In a hiring process'),
  ('gone_quiet', 'Gone quiet'),
  ('closed', 'Closed')
on conflict (status) do nothing;

-- ---------------------------------------------------------------------------
-- Access: the dashboard reads, only the service key writes (see 0002)
-- ---------------------------------------------------------------------------

revoke all on public.status_labels from anon, authenticated;
grant select on public.status_labels to authenticated;
grant select, insert, update on public.status_labels to service_role;

alter table public.status_labels enable row level security;

drop policy if exists "owner reads status_labels" on public.status_labels;
create policy "owner reads status_labels" on public.status_labels
  for select to authenticated using (public.is_app_owner());
