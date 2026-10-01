-- Job-search tracker — the read model behind the dashboard and the morning
-- e-mail: one row per relevant person, with the owner's manual corrections
-- already applied.
--
-- security_invoker makes the view run with the caller's own permissions, so the
-- row-level security rules of the underlying tables still apply.

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
    coalesce(ovr.due_date, st.due_date) < current_date
      and coalesce(ovr.waiting_on, st.waiting_on) is distinct from 'nobody'::public.waiting_on,
    false
  )                                                 as is_overdue,
  (ovr.person_id is not null)                       as has_override
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
  'One row per relevant person. Manual overrides win over the AI assessment.';

grant select on public.people_overview to authenticated;
