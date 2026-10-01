-- Two new ways a run can start: GitHub Actions and the dashboard's "Refresh now".
--
-- The daily run now normally runs on GitHub Actions ('github'), and the owner
-- can ask for an extra run between two mornings that collects and assesses
-- what is new without sending the summary ('refresh'). The Claude cloud
-- routine ('cloud'), the Mac ('mac') and a run by hand ('manual') stay.
--
-- The column becomes an enum, like run_logs.status, instead of text with a
-- check. Besides naming the closed list in one place, an enum lets the set-up
-- see from outside whether this file has been applied: the data API refuses an
-- unknown enum value, while a check constraint is invisible to a read.
--
-- Safe to run twice: the type is created only when missing, the old check is
-- dropped only if it is still there, and the column is converted only while it
-- is still text.

do $$
begin
  if not exists (
    select 1
      from pg_catalog.pg_type t
      join pg_catalog.pg_namespace n on n.oid = t.typnamespace
     where n.nspname = 'public'
       and t.typname = 'run_trigger'
  ) then
    create type public.run_trigger as enum ('cloud', 'mac', 'manual', 'github', 'refresh');
  end if;
end;
$$;

alter table public.run_logs drop constraint if exists run_logs_trigger_check;

do $$
begin
  if exists (
    select 1
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'run_logs'
       and column_name = 'trigger'
       and data_type = 'text'
  ) then
    alter table public.run_logs
      alter column "trigger" type public.run_trigger
      using "trigger"::public.run_trigger;
  end if;
end;
$$;
