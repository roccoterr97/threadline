-- Job-search tracker — "overdue" split in two (Plan 9).
--
-- Until now a passed follow-up date counted as overdue whoever owed the next
-- move, so people who simply had not answered the owner filled the overdue
-- list. Now:
--   is_overdue   — the owner owes the reply and its date has passed;
--   is_chase_due — they owe the reply and the date to chase them has passed.
--
-- create or replace keeps every existing column in place; Postgres only lets a
-- view gain columns at the end, so is_chase_due comes last. Safe to run twice.

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
    coalesce(ovr.due_date, st.due_date) < current_date
      and coalesce(ovr.waiting_on, st.waiting_on) = 'me'::public.waiting_on,
    false
  )                                                 as is_overdue,
  (ovr.person_id is not null)                       as has_override,
  coalesce(
    coalesce(ovr.due_date, st.due_date) < current_date
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
