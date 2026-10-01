-- Threadline — let "Refresh now" take its cool-down in one step that only one
-- press can win.
--
-- Until now the Edge Function `refresh-now` read the newest request, decided,
-- started the run, and only then added its row. Two presses a moment apart
-- both read "nothing recent" and both started a run. Now the function adds its
-- row first, and the database refuses a second row whose cool-down overlaps
-- one already there: of two simultaneous presses exactly one gets in, and only
-- that one asks the runner. When the runner refuses, the function deletes its
-- own row again, so a failed attempt does not make the owner wait.
--
-- The cool-down's length (10 minutes) is set here, by the database, so the
-- dashboard cannot shorten it: the owner may still insert only `target`. The
-- function's REFRESH_COOLDOWN_MINUTES must stay equal; a backend test checks.
--
-- Rows written before this file get an empty cool-down (it ends where it
-- starts), so earlier requests, which may overlap one another, can never
-- conflict here.
--
-- Safe to run twice.

alter table public.refresh_requests add column if not exists cooldown_until timestamptz;

update public.refresh_requests
   set cooldown_until = requested_at
 where cooldown_until is null;

alter table public.refresh_requests
  alter column cooldown_until set default (now() + interval '10 minutes'),
  alter column cooldown_until set not null;

comment on column public.refresh_requests.cooldown_until is
  'Until when no other refresh may start. Two requests whose cool-downs overlap are refused.';

alter table public.refresh_requests
  drop constraint if exists refresh_requests_cooldown_after_request;
alter table public.refresh_requests
  add constraint refresh_requests_cooldown_after_request
  check (cooldown_until >= requested_at);

-- The guarantee itself. A range type needs no extension for this index.
alter table public.refresh_requests
  drop constraint if exists refresh_requests_one_per_cooldown;
alter table public.refresh_requests
  add constraint refresh_requests_one_per_cooldown
  exclude using gist (tstzrange(requested_at, cooldown_until, '[)') with &&);

-- ---------------------------------------------------------------------------
-- Access: the owner may now also delete a request, which the function does
-- only for its own row when the runner refused to start the run. Reading and
-- inserting `target` are unchanged from 0013; the public key still gets nothing.
-- ---------------------------------------------------------------------------

grant delete on public.refresh_requests to authenticated;

drop policy if exists "owner withdraws refresh_requests" on public.refresh_requests;
create policy "owner withdraws refresh_requests" on public.refresh_requests
  for delete to authenticated using (public.is_app_owner());
