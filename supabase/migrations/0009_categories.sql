-- Conversation Tracker — categories the owner defines (Plan 19).
--
-- The kind of person someone is ("Startup", "Investor", "Network" for a job
-- search; "Prospect", "Customer" for sales…) was a fixed enum, copied into the
-- Python code and the dashboard. It becomes data, and the owner edits it on the
-- dashboard's Settings page (or with `tracker profile choose`). No rule in the
-- database or the jobs branches on a category, so any list is safe. Now:
--   * `categories` is the owner's list and the source of truth. It is seeded
--     with the four values that existed before, with today's labels and
--     colours, so nothing changes on screen. The signed-in owner may add, edit,
--     reorder, archive and delete rows; the Python jobs write it with the
--     service key;
--   * `category_suggestions` holds the chosen preset's suggestions, which the
--     dashboard offers as one-tap additions. Only the Python jobs write it;
--   * `people.person_type` and `person_overrides.person_type` become text that
--     must name a category (foreign key, so a category somebody has cannot be
--     deleted — it is archived instead). Existing rows keep their values;
--   * the `person_type` enum is dropped;
--   * `people_overview` is recreated exactly as 0008 left it (it has to be
--     dropped while the column changes type);
--   * the reserved category `unknown` can never be changed or removed, and at
--     most eight other categories can be in use at once;
--   * `app_settings.preset` remembers the preset the owner chose, so the cloud
--     run words the guide the same way without a file of its own.
--
-- Safe to run twice. Runs inside one transaction.

-- ---------------------------------------------------------------------------
-- The owner's categories
-- ---------------------------------------------------------------------------

create table if not exists public.categories (
  id uuid primary key default gen_random_uuid(),
  -- 'all' is not a category: the dashboard's filters use it for "every one".
  key text not null unique check (key ~ '^[a-z][a-z0-9_]{0,30}$' and key <> 'all'),
  label text not null check (btrim(label) <> '' and char_length(label) <= 40),
  group_label text not null check (btrim(group_label) <> '' and char_length(group_label) <= 40),
  description text not null default '' check (char_length(description) <= 1000),
  colour text not null check (
    colour in ('violet', 'cyan', 'orange', 'pink', 'indigo', 'teal', 'olive', 'brown', 'grey')
  ),
  sort_order integer not null default 0 check (sort_order between 0 and 1000),
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- `unknown` is always last and always offered; nothing else sits at 1000.
  constraint categories_unknown_last check ((key = 'unknown') = (sort_order = 1000)),
  constraint categories_unknown_never_archived check (key <> 'unknown' or archived_at is null)
);

comment on table public.categories is
  'The kinds of person the owner sorts people into. Edited by the owner on the '
  'dashboard and by the Python jobs with the service key. `unknown` always exists.';

comment on column public.categories.colour is
  'A palette slot name. The dashboard maps each slot to a light and a dark colour.';

comment on column public.categories.archived_at is
  'Set when the owner removed the category while people still had it. Such a '
  'category still labels those people but is no longer offered as a choice.';

drop trigger if exists categories_set_updated_at on public.categories;
create trigger categories_set_updated_at
  before update on public.categories
  for each row execute function public.set_updated_at();

-- Two rules a check constraint cannot express, because they look at the row
-- before the change or at the other rows:
--   * every person starts as `unknown` (the column default below), so that row
--     must stay exactly as seeded;
--   * the dashboard's grid is designed for at most eight categories besides
--     `unknown`, so a ninth cannot be added or brought back from the archive.
create or replace function public.categories_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    if old.key = 'unknown' then
      raise exception using
        errcode = 'check_violation',
        message = 'the category "unknown" is reserved and cannot be removed';
    end if;
    return old;
  end if;
  if tg_op = 'UPDATE' and old.key = 'unknown'
     and (new.key, new.label, new.group_label, new.description, new.colour,
          new.sort_order, new.archived_at)
         is distinct from
         (old.key, old.label, old.group_label, old.description, old.colour,
          old.sort_order, old.archived_at) then
    raise exception using
      errcode = 'check_violation',
      message = 'the category "unknown" is reserved and cannot be changed';
  end if;
  if new.key <> 'unknown' and new.archived_at is null and (
       select count(*)
         from public.categories c
        where c.archived_at is null
          and c.key <> 'unknown'
          and c.key <> new.key
     ) >= 8 then
    raise exception using
      errcode = 'check_violation',
      message = 'at most 8 categories can be in use at once';
  end if;
  return new;
end;
$$;

comment on function public.categories_guard() is
  'Keeps the reserved category "unknown" unchanged and at most 8 other categories in use.';

drop trigger if exists categories_guard on public.categories;
create trigger categories_guard
  before insert or update or delete on public.categories
  for each row execute function public.categories_guard();

-- The values the enum had, with the labels and colours the dashboard showed.
-- Only into an empty table: running this file again must not bring back a
-- category the owner has since removed.
insert into public.categories (key, label, group_label, description, colour, sort_order)
select seed.key, seed.label, seed.group_label, seed.description, seed.colour, seed.sort_order
  from (values
    ('startup', 'Startup', 'Startups',
     'Someone who works at a startup: founder, executive, employee, in-house recruiter.',
     'violet', 10),
    ('vc', 'Investor', 'Investors',
     'Someone at a fund: talent or people partner, investor, platform team.',
     'cyan', 20),
    ('network', 'Network', 'Network',
     'A friend, a former colleague, anyone who can introduce you rather than hire you.',
     'orange', 30),
    ('unknown', 'Not known', 'Unknown',
     'Not clear from the conversation yet.',
     'grey', 1000)
  ) as seed (key, label, group_label, description, colour, sort_order)
 where not exists (select 1 from public.categories);

-- ---------------------------------------------------------------------------
-- The chosen preset's suggestions
-- ---------------------------------------------------------------------------

create table if not exists public.category_suggestions (
  id uuid primary key default gen_random_uuid(),
  key text not null unique check (
    key ~ '^[a-z][a-z0-9_]{0,30}$' and key not in ('all', 'unknown')
  ),
  label text not null check (btrim(label) <> '' and char_length(label) <= 40),
  group_label text not null check (btrim(group_label) <> '' and char_length(group_label) <= 40),
  description text not null default '' check (char_length(description) <= 1000),
  colour text not null check (
    colour in ('violet', 'cyan', 'orange', 'pink', 'indigo', 'teal', 'olive', 'brown', 'grey')
  ),
  sort_order integer not null default 0 check (sort_order between 0 and 999),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.category_suggestions is
  'The categories the chosen preset suggests. Written by `tracker profile apply`; '
  'the dashboard offers the ones not yet in `categories` as one-tap additions.';

drop trigger if exists category_suggestions_set_updated_at on public.category_suggestions;
create trigger category_suggestions_set_updated_at
  before update on public.category_suggestions
  for each row execute function public.set_updated_at();

-- The job-search preset's suggestions, until `tracker profile apply` writes the
-- chosen preset's. Only into an empty table, like the categories above.
insert into public.category_suggestions (key, label, group_label, description, colour, sort_order)
select c.key, c.label, c.group_label, c.description, c.colour, c.sort_order
  from public.categories c
 where c.key in ('startup', 'vc', 'network')
   and not exists (select 1 from public.category_suggestions);

-- ---------------------------------------------------------------------------
-- The chosen preset
-- ---------------------------------------------------------------------------

alter table public.app_settings
  add column if not exists preset text
  check (preset is null or preset ~ '^[a-z][a-z_]{0,40}$');

comment on column public.app_settings.preset is
  'The preset the owner chose with `tracker profile choose`. Words the guide '
  'when there is no profile file. Null means the job-search preset.';

-- ---------------------------------------------------------------------------
-- person_type becomes a category key
-- ---------------------------------------------------------------------------

-- The view reads people.person_type, and a column a view depends on cannot
-- change type. It is recreated below exactly as 0008 defined it.
drop view if exists public.people_overview;

-- The old default is an enum literal; it is set again once the column is text.
alter table public.people alter column person_type drop default;
alter table public.people alter column person_type type text using person_type::text;
alter table public.people alter column person_type set default 'unknown';

alter table public.person_overrides
  alter column person_type type text using person_type::text;

alter table public.people drop constraint if exists people_person_type_fkey;
alter table public.people
  add constraint people_person_type_fkey foreign key (person_type)
  references public.categories (key) on update cascade on delete restrict;

alter table public.person_overrides drop constraint if exists person_overrides_person_type_fkey;
alter table public.person_overrides
  add constraint person_overrides_person_type_fkey foreign key (person_type)
  references public.categories (key) on update cascade on delete restrict;

drop type if exists public.person_type;

-- ---------------------------------------------------------------------------
-- people_overview, exactly as 0008 left it
-- ---------------------------------------------------------------------------

create view public.people_overview
with (security_invoker = true)
as
select
  p.id                                              as person_id,
  p.full_name,
  p.role_title,
  o.name                                            as organisation_name,
  coalesce(ovr.person_type, p.person_type)          as person_type,
  coalesce(ovr.status, st.status)                   as status,
  coalesce(ovr.waiting_on, st.waiting_on)           as waiting_on,
  coalesce(ovr.next_action, st.next_action)         as next_action,
  coalesce(ovr.due_date, st.due_date)               as due_date,
  st.summary,
  st.signal,
  st.confidence,
  st.assessed_at,
  stats.last_contact_at,
  coalesce(stats.channels, array[]::public.channel[]) as channels,
  coalesce(stats.message_count, 0)                  as message_count,
  coalesce(
    coalesce(ovr.due_date, st.due_date) < public.owner_today()
      and coalesce(ovr.waiting_on, st.waiting_on) = 'me'::public.waiting_on,
    false
  )                                                 as is_overdue,
  (ovr.person_id is not null)                       as has_override,
  coalesce(
    coalesce(ovr.due_date, st.due_date) < public.owner_today()
      and coalesce(ovr.waiting_on, st.waiting_on) = 'them'::public.waiting_on,
    false
  )                                                 as is_chase_due
from public.people p
left join public.organisations o on o.id = p.organisation_id
left join public.person_states st on st.person_id = p.id
left join public.person_overrides ovr on ovr.person_id = p.id
left join lateral (
  select
    max(m.sent_at)                as last_contact_at,
    array_agg(distinct c.channel) as channels,
    count(m.id)                   as message_count
  from public.conversations c
  join public.messages m on m.conversation_id = c.id
  where c.person_id = p.id
) stats on true
where p.relevance = 'relevant';

comment on view public.people_overview is
  'One row per relevant person. Manual overrides win over the AI assessment. '
  'is_overdue: a reply the owner owes is late. is_chase_due: they owe the reply '
  'and the chase date has passed.';

grant select on public.people_overview to authenticated;

-- ---------------------------------------------------------------------------
-- Access (see 0002): the owner edits categories; suggestions are read-only
-- ---------------------------------------------------------------------------

revoke all on public.categories from anon, authenticated;
grant select on public.categories to authenticated;
-- A new row names every column the owner may set; an edit can never change the
-- key, which is what people and overrides point at. Removing a category that
-- somebody still has is refused by the foreign keys, so the dashboard archives
-- it instead.
grant insert (key, label, group_label, description, colour, sort_order, archived_at)
  on public.categories to authenticated;
grant update (label, group_label, description, colour, sort_order, archived_at)
  on public.categories to authenticated;
grant delete on public.categories to authenticated;
-- Granted explicitly so the Python jobs do not depend on Supabase's defaults.
grant select, insert, update, delete on public.categories to service_role;

alter table public.categories enable row level security;

drop policy if exists "owner reads categories" on public.categories;
create policy "owner reads categories" on public.categories
  for select to authenticated using (public.is_app_owner());

drop policy if exists "owner adds categories" on public.categories;
create policy "owner adds categories" on public.categories
  for insert to authenticated with check (public.is_app_owner());

drop policy if exists "owner edits categories" on public.categories;
create policy "owner edits categories" on public.categories
  for update to authenticated using (public.is_app_owner()) with check (public.is_app_owner());

drop policy if exists "owner removes categories" on public.categories;
create policy "owner removes categories" on public.categories
  for delete to authenticated using (public.is_app_owner());

revoke all on public.category_suggestions from anon, authenticated;
grant select on public.category_suggestions to authenticated;
grant select, insert, update, delete on public.category_suggestions to service_role;

alter table public.category_suggestions enable row level security;

drop policy if exists "owner reads category_suggestions" on public.category_suggestions;
create policy "owner reads category_suggestions" on public.category_suggestions
  for select to authenticated using (public.is_app_owner());

-- As 0011 requires of every new function: nobody but the roles whose writes
-- fire the trigger keeps EXECUTE.
revoke execute on function public.categories_guard() from public, anon;
grant execute on function public.categories_guard() to authenticated, service_role;
