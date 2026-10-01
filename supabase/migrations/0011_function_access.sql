-- Who may call the database functions.
--
-- PostgreSQL gives EXECUTE on every new function to PUBLIC, and Supabase also
-- grants it to anon and authenticated by default. 0002 revoked it from anon and
-- authenticated only, so PUBLIC (and through it anon, the role of anybody
-- holding the public key without signing in) kept it; the function added in
-- 0007 was never revoked at all. This migration takes EXECUTE away from PUBLIC
-- and anon on every function the earlier migrations created, then gives back
-- exactly what each function needs.
--
-- Safe to run twice: revoking what is not granted and granting what already
-- is are both no-ops.

-- ---------------------------------------------------------------------------
-- is_app_owner(): the check inside every row-level security policy.
--
-- Every policy in 0002 is written "to authenticated ... using
-- (public.is_app_owner())", and a policy expression runs as the role that
-- issued the query. The signed-in owner's queries run as authenticated, so
-- authenticated MUST keep EXECUTE: without it every read and every answer
-- from the dashboard would fail with "permission denied for function". The
-- function is security definer and only reports whether the caller is the
-- owner, so keeping it callable by authenticated reveals nothing more.
--
-- anon has no policy that uses it and needs no answer from it. The Python jobs
-- use the service role, which bypasses row-level security; the explicit grant
-- keeps it working if that ever changes.
-- ---------------------------------------------------------------------------

revoke execute on function public.is_app_owner() from public, anon;
grant execute on function public.is_app_owner() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Trigger functions: set_updated_at() (0001) and apply_relevance_answer()
-- (0007).
--
-- A function that returns "trigger" cannot be called directly — PostgreSQL
-- refuses with "trigger functions can only be called as triggers" — so these
-- grants expose nothing through the API. They are kept for the roles whose
-- writes fire the triggers (the dashboard as authenticated, the jobs as
-- service_role), exactly as 0002 and 0007 intended, so this migration changes
-- no behaviour for them. anon writes nothing and loses EXECUTE.
-- ---------------------------------------------------------------------------

revoke execute on function public.set_updated_at() from public, anon;
grant execute on function public.set_updated_at() to authenticated, service_role;

revoke execute on function public.apply_relevance_answer() from public, anon;
grant execute on function public.apply_relevance_answer() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Functions added later.
--
-- Stop the Supabase default that grants anon EXECUTE on new functions in the
-- public schema. This applies to functions created by the role running the
-- migration (postgres in the Supabase SQL editor). PostgreSQL's own grant to
-- PUBLIC cannot be switched off per schema, so a later migration that adds a
-- function must still revoke EXECUTE from public and anon itself, as above.
-- ---------------------------------------------------------------------------

alter default privileges in schema public revoke execute on functions from anon;
