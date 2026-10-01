-- Job-search tracker — the Outlook calendar as a third source (Plan 11).
--
-- A meeting with somebody other than the owner becomes a thread on the new
-- 'calendar' channel, and the daily run records reading it as its own step,
-- so a failed calendar read is reported without hiding the mailbox result.
--
-- "if not exists" makes the file safe to run twice.

alter type public.channel add value if not exists 'calendar';
alter type public.run_step add value if not exists 'collect_calendar';
