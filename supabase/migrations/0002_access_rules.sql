-- Job-search tracker — who may read and write what.
--
-- There is exactly one human user. The owner's login identifier is inserted into
-- app_owner after the first sign-in; until then the table is empty and
-- nobody can read anything through the public key.
--
-- Two mechanisms work together:
--   * GRANTs decide which columns a role may touch at all;
--   * row-level security decides which rows, and requires the caller to be the
--     owner recorded in app_owner.
-- The Python jobs use the service key, which bypasses row-level security.

-- ---------------------------------------------------------------------------
-- The single owner
-- ---------------------------------------------------------------------------

create table public.app_owner (
  user_id uuid primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger app_owner_set_updated_at
  before update on public.app_owner
  for each row execute function public.set_updated_at();

-- Security definer so a logged-in user can be checked against the table
-- without being allowed to read it.
create or replace function public.is_app_owner()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.app_owner where user_id = (select auth.uid())
  );
$$;

-- ---------------------------------------------------------------------------
-- Start from nothing: Supabase grants the public schema to anon and
-- authenticated by default. Every permission below is then given back on
-- purpose. New tables added by later migrations must grant explicitly.
-- ---------------------------------------------------------------------------

revoke all on all tables in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;

grant execute on function public.is_app_owner() to authenticated;
-- Fires on every allowed update below, so the role must keep it.
grant execute on function public.set_updated_at() to authenticated;

-- ---------------------------------------------------------------------------
-- Reading: everything except the secrets and the owner table.
-- ---------------------------------------------------------------------------

grant select on
  public.organisations,
  public.people,
  public.person_identities,
  public.conversations,
  public.messages,
  public.person_states,
  public.person_overrides,
  public.review_items,
  public.run_logs,
  public.run_step_logs
to authenticated;

-- ---------------------------------------------------------------------------
-- Writing: only the three things the owner corrects by hand.
-- ---------------------------------------------------------------------------

grant insert, update, delete on public.person_overrides to authenticated;
grant update (answer, answered_at) on public.review_items to authenticated;
grant update (relevance) on public.people to authenticated;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

alter table public.app_owner enable row level security;
alter table public.app_secrets enable row level security;
alter table public.organisations enable row level security;
alter table public.people enable row level security;
alter table public.person_identities enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.person_states enable row level security;
alter table public.person_overrides enable row level security;
alter table public.review_items enable row level security;
alter table public.run_logs enable row level security;
alter table public.run_step_logs enable row level security;

-- app_owner and app_secrets deliberately have no policy at all: with row-level
-- security on and nothing granted, anon and authenticated see no rows.

create policy "owner reads organisations" on public.organisations
  for select to authenticated using (public.is_app_owner());

create policy "owner reads people" on public.people
  for select to authenticated using (public.is_app_owner());

create policy "owner updates people relevance" on public.people
  for update to authenticated using (public.is_app_owner()) with check (public.is_app_owner());

create policy "owner reads person_identities" on public.person_identities
  for select to authenticated using (public.is_app_owner());

create policy "owner reads conversations" on public.conversations
  for select to authenticated using (public.is_app_owner());

create policy "owner reads messages" on public.messages
  for select to authenticated using (public.is_app_owner());

create policy "owner reads person_states" on public.person_states
  for select to authenticated using (public.is_app_owner());

create policy "owner reads person_overrides" on public.person_overrides
  for select to authenticated using (public.is_app_owner());

create policy "owner inserts person_overrides" on public.person_overrides
  for insert to authenticated with check (public.is_app_owner());

create policy "owner updates person_overrides" on public.person_overrides
  for update to authenticated using (public.is_app_owner()) with check (public.is_app_owner());

create policy "owner deletes person_overrides" on public.person_overrides
  for delete to authenticated using (public.is_app_owner());

create policy "owner reads review_items" on public.review_items
  for select to authenticated using (public.is_app_owner());

create policy "owner answers review_items" on public.review_items
  for update to authenticated using (public.is_app_owner()) with check (public.is_app_owner());

create policy "owner reads run_logs" on public.run_logs
  for select to authenticated using (public.is_app_owner());

create policy "owner reads run_step_logs" on public.run_step_logs
  for select to authenticated using (public.is_app_owner());
