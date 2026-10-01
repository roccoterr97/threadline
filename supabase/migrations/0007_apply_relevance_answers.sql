-- Job-search tracker — apply the owner's relevance answers at once.
--
-- Until now a "yes" to "Is X part of your job search?" only took effect once
-- that person wrote again, so people the owner had confirmed stayed hidden. From here
-- on the answer changes the person the moment it is given, and the answers
-- already given are applied once.
--
-- Safe to run twice.

-- ---------------------------------------------------------------------------
-- A relevance answer changes the person at once: yes → relevant, no → noise.
-- ---------------------------------------------------------------------------

create or replace function public.apply_relevance_answer()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.kind = 'relevance' and new.person_id is not null and new.conversation_id is null
     and new.answer is not null and new.answer is distinct from old.answer then
    update public.people
       set relevance = case new.answer when 'yes' then 'relevant'::public.relevance
                                       else 'noise'::public.relevance end
     where id = new.person_id;
  end if;
  return new;
end;
$$;

grant execute on function public.apply_relevance_answer() to authenticated;

drop trigger if exists review_items_apply_relevance_answer on public.review_items;
create trigger review_items_apply_relevance_answer
  after update of answer on public.review_items
  for each row execute function public.apply_relevance_answer();

-- The answers already given before this trigger existed.
update public.people p
   set relevance = case r.answer when 'yes' then 'relevant'::public.relevance
                                 else 'noise'::public.relevance end
  from public.review_items r
 where r.kind = 'relevance'
   and r.person_id = p.id
   and r.conversation_id is null
   and r.answer is not null
   and p.relevance = 'unsure';
