-- Threadline — remember when the dashboard's "Refresh now" button last started
-- a run.
--
-- The Edge Function `refresh-now` reads the newest row to refuse a second
-- refresh within a few minutes of the first (the cool-down lives in the
-- function), and adds a row each time it starts one. It acts as the signed-in
-- owner, never with the service key, so the owner needs read and insert here —
-- nothing else. Rows are never updated or deleted by the dashboard.
--
-- Safe to run twice.

create table if not exists public.refresh_requests (
  id uuid primary key default gen_random_uuid(),
  requested_at timestamptz not null default now(),
  target text not null check (target in ('github', 'claude_routine')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.refresh_requests is
  'One row per extra run started from the dashboard''s "Refresh now" button.';
comment on column public.refresh_requests.target is
  'Which runner was asked: the GitHub Actions workflow or the Claude cloud routine.';

-- The function reads only the newest row.
create index if not exists refresh_requests_requested_at_idx
  on public.refresh_requests (requested_at desc);

drop trigger if exists refresh_requests_set_updated_at on public.refresh_requests;
create trigger refresh_requests_set_updated_at
  before update on public.refresh_requests
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Access: the owner reads and adds; the public key gets nothing.
-- ---------------------------------------------------------------------------

alter table public.refresh_requests enable row level security;

revoke all on public.refresh_requests from anon, authenticated;
grant select on public.refresh_requests to authenticated;
grant insert (target) on public.refresh_requests to authenticated;
grant select, insert, update, delete on public.refresh_requests to service_role;

drop policy if exists "owner reads refresh_requests" on public.refresh_requests;
create policy "owner reads refresh_requests" on public.refresh_requests
  for select to authenticated using (public.is_app_owner());

drop policy if exists "owner records refresh_requests" on public.refresh_requests;
create policy "owner records refresh_requests" on public.refresh_requests
  for insert to authenticated with check (public.is_app_owner());
