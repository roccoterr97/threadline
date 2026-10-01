-- Threadline — no two categories share a name or a group name, whatever the
-- capitals or the spaces around it.
--
-- The dashboard already refuses "customer" next to "Customer", but only
-- against the list it last loaded: two tabs, or the dashboard and
-- `tracker profile choose`, could still save the same name twice, and two
-- identical columns and filter buttons would follow. Now the database refuses
-- it too, with one unique index on each of the two names, compared in lower
-- case and without surrounding spaces.
--
-- Before the indexes can exist, names that already clash are told apart: the
-- first category to have a name keeps it, and each later one gets " (2)",
-- " (3)"… added (shortened first if it would pass 40 characters). The reserved
-- category `unknown` always keeps its names.
--
-- The reserved category's group name changes from "Unknown" to "Not known",
-- its one-person name, so the database says what the dashboard shows. Only
-- the seeded value is replaced. The guard trigger from 0009 refuses every
-- change to that row, on purpose, so this file switches the guard off for the
-- one update and straight back on, inside one statement: the table stays
-- locked while it is off, so nobody else can write in that moment, and if the
-- update fails the guard is never left off.
--
-- Safe to run twice.

-- ---------------------------------------------------------------------------
-- The reserved category's group name
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (
    select 1
      from public.categories
     where key = 'unknown'
       and group_label = 'Unknown'
  ) then
    alter table public.categories disable trigger categories_guard;
    update public.categories
       set group_label = 'Not known'
     where key = 'unknown'
       and group_label = 'Unknown';
    alter table public.categories enable trigger categories_guard;
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- Names that already clash
-- ---------------------------------------------------------------------------

-- The column names come from the fixed list below, never from data.
do $$
declare
  name_column text;
  clash record;
  suffix text;
  candidate text;
  number integer;
  taken boolean;
begin
  foreach name_column in array array['label', 'group_label'] loop
    for clash in execute format(
      'select id, %1$I as name,
              row_number() over (
                partition by lower(btrim(%1$I))
                order by (key = %2$L) desc, created_at, id
              ) as position
         from public.categories',
      name_column, 'unknown'
    ) loop
      continue when clash.position = 1;
      number := clash.position;
      loop
        suffix := format(' (%s)', number);
        candidate := rtrim(left(btrim(clash.name), 40 - char_length(suffix))) || suffix;
        execute format(
          'select exists (select 1 from public.categories where lower(btrim(%I)) = lower($1))',
          name_column
        ) into taken using candidate;
        exit when not taken;
        number := number + 1;
      end loop;
      execute format('update public.categories set %I = $1 where id = $2', name_column)
        using candidate, clash.id;
    end loop;
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- The guarantee itself
-- ---------------------------------------------------------------------------

create unique index if not exists categories_label_unique
  on public.categories (lower(btrim(label)));

create unique index if not exists categories_group_label_unique
  on public.categories (lower(btrim(group_label)));

comment on index public.categories_label_unique is
  'No two categories share a name, ignoring capitals and surrounding spaces.';

comment on index public.categories_group_label_unique is
  'No two categories share a group name, ignoring capitals and surrounding spaces.';
