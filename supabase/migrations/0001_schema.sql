-- Job-search tracker — tables, enums and indexes.
--
-- Every table carries id / created_at / updated_at. All timestamps are UTC and
-- stored as timestamptz; conversion to local time happens in the dashboard.
-- A message judged noise keeps no subject and no body: only its identifier,
-- its date and the decision, so it is never processed twice.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums: the closed sets of values, mirrored one for one in Python.
-- ---------------------------------------------------------------------------

create type public.channel as enum ('linkedin', 'email');
create type public.direction as enum ('inbound', 'outbound');
create type public.person_type as enum ('startup', 'vc', 'network', 'unknown');
create type public.relevance as enum ('relevant', 'noise', 'unsure');
create type public.contact_status as enum (
  'contacted_no_reply',
  'in_conversation',
  'meeting_planned',
  'in_hiring_process',
  'gone_quiet',
  'closed'
);
create type public.waiting_on as enum ('me', 'them', 'nobody');
create type public.signal as enum ('positive', 'neutral', 'cold');
create type public.review_kind as enum ('relevance', 'same_person');
create type public.review_answer as enum ('yes', 'no');
create type public.run_status as enum ('running', 'success', 'partial', 'failed');
create type public.run_step as enum (
  'collect_linkedin',
  'collect_email',
  'assess',
  'summary_email'
);

-- ---------------------------------------------------------------------------
-- Keeps updated_at honest without the application having to remember.
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.organisations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kind text check (kind in ('startup', 'vc_fund', 'other')),
  email_domain text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.people (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  person_type public.person_type not null default 'unknown',
  role_title text,
  organisation_id uuid references public.organisations (id) on delete set null,
  relevance public.relevance not null default 'unsure',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index people_organisation_id_idx on public.people (organisation_id);
create index people_relevance_idx on public.people (relevance);

create table public.person_identities (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references public.people (id) on delete cascade,
  channel public.channel not null,
  identifier text not null,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint person_identities_channel_identifier_key unique (channel, identifier)
);

create index person_identities_person_id_idx on public.person_identities (person_id);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  person_id uuid references public.people (id) on delete set null,
  channel public.channel not null,
  source_conversation_id text not null,
  subject text,
  relevance public.relevance not null default 'unsure',
  relevance_decided_by text check (relevance_decided_by in ('rule', 'ai', 'owner')),
  first_message_at timestamptz,
  last_message_at timestamptz,
  last_inbound_at timestamptz,
  last_outbound_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint conversations_channel_source_key unique (channel, source_conversation_id),
  constraint conversations_noise_keeps_no_subject check (relevance <> 'noise' or subject is null)
);

create index conversations_person_id_idx on public.conversations (person_id);
create index conversations_last_message_at_idx on public.conversations (last_message_at desc);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  source_message_id text not null,
  direction public.direction not null,
  sent_at timestamptz not null,
  sender_identifier text,
  body text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint messages_conversation_source_key unique (conversation_id, source_message_id)
);

create index messages_conversation_sent_at_idx on public.messages (conversation_id, sent_at desc);

create table public.person_states (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null unique references public.people (id) on delete cascade,
  status public.contact_status not null,
  waiting_on public.waiting_on not null,
  next_action text,
  due_date date,
  summary text,
  signal public.signal not null default 'neutral',
  confidence numeric(3, 2) not null check (confidence >= 0 and confidence <= 1),
  assessed_at timestamptz not null,
  assessed_through timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index person_states_due_date_idx on public.person_states (due_date);

create table public.person_overrides (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null unique references public.people (id) on delete cascade,
  status public.contact_status,
  waiting_on public.waiting_on,
  next_action text,
  due_date date,
  person_type public.person_type,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.review_items (
  id uuid primary key default gen_random_uuid(),
  kind public.review_kind not null,
  person_id uuid references public.people (id) on delete cascade,
  conversation_id uuid references public.conversations (id) on delete cascade,
  other_person_id uuid references public.people (id) on delete cascade,
  question text not null,
  answer public.review_answer,
  answered_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint review_items_answer_has_time check (
    (answer is null and answered_at is null) or (answer is not null and answered_at is not null)
  ),
  constraint review_items_same_person_needs_other check (
    kind <> 'same_person' or other_person_id is not null
  )
);

create index review_items_unanswered_idx on public.review_items (created_at) where answer is null;

create table public.run_logs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status public.run_status not null,
  "trigger" text not null check ("trigger" in ('cloud', 'mac', 'manual')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index run_logs_started_at_idx on public.run_logs (started_at desc);

-- Counts and error codes only: never message text, never a secret.
create table public.run_step_logs (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.run_logs (id) on delete cascade,
  step public.run_step not null,
  status public.run_status not null,
  items_found integer,
  items_new integer,
  error_code text,
  error_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index run_step_logs_run_id_idx on public.run_step_logs (run_id);

-- Reachable only with the service key; see 0002_access_rules.sql.
create table public.app_secrets (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  encrypted_value text not null,
  rotated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------

create trigger organisations_set_updated_at
  before update on public.organisations
  for each row execute function public.set_updated_at();

create trigger people_set_updated_at
  before update on public.people
  for each row execute function public.set_updated_at();

create trigger person_identities_set_updated_at
  before update on public.person_identities
  for each row execute function public.set_updated_at();

create trigger conversations_set_updated_at
  before update on public.conversations
  for each row execute function public.set_updated_at();

create trigger messages_set_updated_at
  before update on public.messages
  for each row execute function public.set_updated_at();

create trigger person_states_set_updated_at
  before update on public.person_states
  for each row execute function public.set_updated_at();

create trigger person_overrides_set_updated_at
  before update on public.person_overrides
  for each row execute function public.set_updated_at();

create trigger review_items_set_updated_at
  before update on public.review_items
  for each row execute function public.set_updated_at();

create trigger run_logs_set_updated_at
  before update on public.run_logs
  for each row execute function public.set_updated_at();

create trigger run_step_logs_set_updated_at
  before update on public.run_step_logs
  for each row execute function public.set_updated_at();

create trigger app_secrets_set_updated_at
  before update on public.app_secrets
  for each row execute function public.set_updated_at();
