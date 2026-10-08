-- Threadline — start the morning run on time, from Supabase.
--
-- GitHub starts a scheduled workflow when it has room, and for some
-- repositories that is hours after the time in the workflow's `cron` line. So
-- the database starts the daily run instead: every 15 minutes a pg_cron job
-- calls the `refresh-now` Edge Function's scheduled path
-- (`…/functions/v1/refresh-now/daily-start`). Once the owner's daily time has
-- passed in the owner's time zone, the function asks GitHub to start the
-- workflow in daily mode, at most once per owner-local day. GitHub's own
-- schedule stays as a backup: its gate stops when the day's run already
-- started.
--
-- This file adds:
--   * app_settings.daily_run_time: the owner's daily time. It is 07:00 until
--     `tracker setup schedule` or `tracker setup refresh` copies the
--     workflow's time here.
--   * daily_starts: one row per owner-local day on which the function asked
--     GitHub for the run. The unique date is the claim: of two calls at the
--     same moment only one can add it, and only that one asks GitHub. When
--     GitHub refuses, the function deletes its row again, so the next call,
--     15 minutes later, tries again.
--   * request_daily_start(): what the cron job runs. It reads the function's
--     address and the shared key from Supabase Vault, and does nothing until
--     `tracker setup refresh` has put them there.
--   * save_daily_start_settings(): how `tracker setup refresh` puts them
--     there, with the service key, and makes sure the cron job exists.
--   * daily_start_status(): what `tracker doctor` reads.
--
-- pg_cron, pg_net and Vault come with every Supabase project, on the free
-- plan too. The job, the key header and the function's path are a contract
-- with supabase/functions/refresh-now/daily.ts; a backend test keeps them
-- equal.
--
-- Safe to run twice.

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;
create extension if not exists supabase_vault;

-- ---------------------------------------------------------------------------
-- The owner's daily time
-- ---------------------------------------------------------------------------

alter table public.app_settings
  add column if not exists daily_run_time time not null default '07:00';

comment on column public.app_settings.daily_run_time is
  'The daily run''s time of day, read in time_zone. The set-up copies it from '
  'the GitHub workflow; the on-time morning start reads it.';

-- ---------------------------------------------------------------------------
-- One claim per owner-local day
-- ---------------------------------------------------------------------------

create table if not exists public.daily_starts (
  id uuid primary key default gen_random_uuid(),
  owner_date date not null unique,
  requested_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.daily_starts is
  'One row per day, in the owner''s time zone, on which the on-time morning '
  'start asked GitHub for the daily run. Written by the refresh-now function only.';

drop trigger if exists daily_starts_set_updated_at on public.daily_starts;
create trigger daily_starts_set_updated_at
  before update on public.daily_starts
  for each row execute function public.set_updated_at();

-- Only the function, with the service key, reads and writes it.
alter table public.daily_starts enable row level security;

revoke all on public.daily_starts from anon, authenticated;
grant select, insert, delete on public.daily_starts to service_role;

-- ---------------------------------------------------------------------------
-- What the cron job runs
-- ---------------------------------------------------------------------------

-- Runs as the job's owner (postgres), the only role allowed to call it. The
-- 30-second limit leaves the function time to ask the database and GitHub.
create or replace function public.request_daily_start()
returns bigint
language plpgsql
set search_path = ''
as $$
declare
  target_url text;
  shared_key text;
begin
  select s.decrypted_secret into target_url
    from vault.decrypted_secrets s
   where s.name = 'threadline_daily_start_url';
  select s.decrypted_secret into shared_key
    from vault.decrypted_secrets s
   where s.name = 'threadline_daily_start_key';
  if target_url is null or shared_key is null then
    return null;
  end if;
  return net.http_post(
    url := target_url,
    body := '{}'::jsonb,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Daily-Start-Key', shared_key
    ),
    timeout_milliseconds := 30000
  );
end;
$$;

comment on function public.request_daily_start() is
  'Called every 15 minutes by pg_cron: asks the refresh-now function to start '
  'the daily run if it is due. Does nothing until the set-up saved its settings.';

revoke execute on function public.request_daily_start()
  from public, anon, authenticated, service_role;

-- Creates the job, or puts it back as written here. Scheduling under a name
-- that exists replaces that job, so this is safe to repeat.
create or replace function public.schedule_daily_start()
returns bigint
language sql
set search_path = ''
as $$
  select cron.schedule(
    'threadline-daily-start',
    '*/15 * * * *',
    'select public.request_daily_start()'
  );
$$;

revoke execute on function public.schedule_daily_start()
  from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- How the set-up switches it on
-- ---------------------------------------------------------------------------

-- Adds a Vault secret, or replaces the value of the one with that name.
create or replace function public.put_daily_start_secret(
  secret_name text,
  secret_value text,
  secret_description text
)
returns void
language plpgsql
set search_path = ''
as $$
declare
  existing uuid;
begin
  select s.id into existing from vault.secrets s where s.name = secret_name;
  if existing is null then
    perform vault.create_secret(secret_value, secret_name, secret_description);
  else
    perform vault.update_secret(existing, secret_value, secret_name, secret_description);
  end if;
end;
$$;

revoke execute on function public.put_daily_start_secret(text, text, text)
  from public, anon, authenticated, service_role;

-- Security definer, so the service key can store the two values in Vault and
-- make sure the job exists without being given Vault or pg_cron itself. The
-- address must be the function's scheduled path, so the key can only ever be
-- sent there.
create or replace function public.save_daily_start_settings(
  function_url text,
  shared_key text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if function_url is null
     or function_url !~ '^https://[A-Za-z0-9.-]+/functions/v1/refresh-now/daily-start$' then
    raise exception 'the on-time start address must be the refresh-now function''s daily-start path'
      using errcode = '22023';
  end if;
  if shared_key is null or char_length(shared_key) < 32 then
    raise exception 'the on-time start key must be at least 32 characters'
      using errcode = '22023';
  end if;
  perform public.put_daily_start_secret(
    'threadline_daily_start_url', function_url,
    'Where pg_cron asks for the on-time morning start (Threadline).'
  );
  perform public.put_daily_start_secret(
    'threadline_daily_start_key', shared_key,
    'The key pg_cron proves itself with to the refresh-now function (Threadline).'
  );
  perform public.schedule_daily_start();
end;
$$;

comment on function public.save_daily_start_settings(text, text) is
  'Saves the on-time morning start''s address and key in Vault and makes sure '
  'its cron job exists. Called by tracker setup refresh with the service key.';

revoke execute on function public.save_daily_start_settings(text, text)
  from public, anon, authenticated;
grant execute on function public.save_daily_start_settings(text, text) to service_role;

-- ---------------------------------------------------------------------------
-- What the doctor reads
-- ---------------------------------------------------------------------------

-- Names only, never a secret's value.
create or replace function public.daily_start_status()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'job_scheduled', exists (
      select 1 from cron.job j where j.jobname = 'threadline-daily-start' and j.active
    ),
    'switched_on', (
      select count(*) from vault.secrets s
       where s.name in ('threadline_daily_start_url', 'threadline_daily_start_key')
    ) = 2,
    'daily_run_time', (
      select to_char(a.daily_run_time, 'HH24:MI') from public.app_settings a where a.singleton
    ),
    'time_zone', (select a.time_zone from public.app_settings a where a.singleton),
    'last_started_on', (select max(d.owner_date) from public.daily_starts d)
  );
$$;

comment on function public.daily_start_status() is
  'Whether the on-time morning start is switched on, its time, and the last day it started a run.';

revoke execute on function public.daily_start_status() from public, anon, authenticated;
grant execute on function public.daily_start_status() to service_role;

-- ---------------------------------------------------------------------------
-- The job itself: harmless until the set-up has saved the settings above.
-- ---------------------------------------------------------------------------

select public.schedule_daily_start();
