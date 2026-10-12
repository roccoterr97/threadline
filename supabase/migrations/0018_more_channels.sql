-- Threadline — Telegram, Slack and Teams chats, and a Google calendar.
--
-- Telegram, Slack and Microsoft Teams are new channels: a chat with somebody
-- becomes a thread on its own channel, filed under that person. A Google
-- calendar, read through its private iCal address, adds meetings to the
-- existing 'calendar' channel. Each source is read as its own run step, so one
-- that fails is reported without hiding the others.
--
-- "if not exists" makes the file safe to run twice.

alter type public.channel add value if not exists 'telegram';
alter type public.channel add value if not exists 'slack';
alter type public.channel add value if not exists 'teams';
alter type public.run_step add value if not exists 'collect_google_calendar';
alter type public.run_step add value if not exists 'collect_telegram';
alter type public.run_step add value if not exists 'collect_slack';
alter type public.run_step add value if not exists 'collect_teams';
