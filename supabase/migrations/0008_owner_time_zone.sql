-- Conversation Tracker — "today" is the owner's day, not the server's (Plan 18).
--
-- people_overview decided "overdue" and "time to chase" against current_date,
-- the database server's date, which is UTC on Supabase. For an owner in Tokyo
-- that is still yesterday until nine in the morning, and for an owner in Los
-- Angeles it is already tomorrow from five in the afternoon. Now:
--   * app_settings holds the owner's IANA time zone in exactly one row. The
--     Python jobs write it from OWNER_TIME_ZONE when a daily run starts; the
--     dashboard may read it; nobody else may write it.
--   * public.owner_today() is the date in that zone, UTC when nothing is set.
--   * people_overview is recreated exactly as 0004 left it, with current_date
--     replaced by public.owner_today(). Same columns, same order, same comment,
--     same grant, still security_invoker.
--
-- Safe to run twice.

-- ---------------------------------------------------------------------------
-- The owner's settings: one row, never two
-- ---------------------------------------------------------------------------

create table if not exists public.app_settings (
  id uuid primary key default gen_random_uuid(),
  -- Always true and unique, so a second row cannot exist. It is also the
  -- natural key the Python jobs upsert on.
  singleton boolean not null default true unique check (singleton),
  time_zone text not null default 'UTC',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.app_settings is
  'The owner''s settings the database itself needs. Exactly one row, written '
  'by the Python jobs with the service key.';

comment on column public.app_settings.time_zone is
  'IANA time zone, such as Europe/Rome. Decides what "today" is in people_overview.';

-- A zone Postgres does not know would make every read of people_overview fail,
-- so it is refused when it is written instead: "at time zone" raises for an
-- unknown name.
create or replace function public.app_settings_check_time_zone()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  perform now() at time zone new.time_zone;
  return new;
end;
$$;

drop trigger if exists app_settings_check_time_zone on public.app_settings;
create trigger app_settings_check_time_zone
  before insert or update of time_zone on public.app_settings
  for each row execute function public.app_settings_check_time_zone();

drop trigger if exists app_settings_set_updated_at on public.app_settings;
create trigger app_settings_set_updated_at
  before update on public.app_settings
  for each row execute function public.set_updated_at();

insert into public.app_settings (singleton)
values (true)
on conflict (singleton) do nothing;

-- ---------------------------------------------------------------------------
-- Access: the dashboard reads, only the service key writes (see 0002)
-- ---------------------------------------------------------------------------

revoke all on public.app_settings from anon, authenticated;
grant select on public.app_settings to authenticated;
-- Supabase's default privileges already give the service role these; granted
-- explicitly so the one writer does not depend on them.
grant select, insert, update on public.app_settings to service_role;

alter table public.app_settings enable row level security;

drop policy if exists "owner reads app_settings" on public.app_settings;
create policy "owner reads app_settings" on public.app_settings
  for select to authenticated using (public.is_app_owner());

-- ---------------------------------------------------------------------------
-- The owner's today
-- ---------------------------------------------------------------------------

-- Security invoker on purpose: the dashboard sees the zone through the policy
-- above, the Python jobs through the service key. Anybody else sees no row and
-- gets the UTC date, which reveals nothing.
create or replace function public.owner_today()
returns date
language sql
stable
set search_path = ''
as $$
  select (now() at time zone coalesce(
    (select s.time_zone from public.app_settings s where s.singleton),
    'UTC'
  ))::date;
$$;

comment on function public.owner_today() is
  'Today''s date in the owner''s time zone (app_settings.time_zone), UTC when unset.';

revoke all on function public.owner_today() from public, anon;
grant execute on function public.owner_today() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- people_overview, measured against the owner's today
-- ---------------------------------------------------------------------------

create or replace view public.people_overview
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
