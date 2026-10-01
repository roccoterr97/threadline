-- Job-search tracker — when a calendar meeting takes place (Plan 12).
--
-- A calendar thread's messages are dated when the event was created or last
-- changed, which keeps "last contact" truthful but says nothing about when the
-- meeting happens. The dashboard's "Coming up" strip needs that moment; it is
-- empty for every other thread and for a cancelled meeting.
--
-- "if not exists" makes the file safe to run twice.

alter table public.conversations
  add column if not exists meeting_at timestamptz;

comment on column public.conversations.meeting_at is
  'Calendar threads only: when the meeting starts. Null when cancelled or not a meeting.';

create index if not exists conversations_meeting_at_idx
  on public.conversations (meeting_at)
  where meeting_at is not null;
