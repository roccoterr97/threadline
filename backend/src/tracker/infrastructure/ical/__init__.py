"""Read-only access to a calendar through its secret iCalendar (``.ics``) address.

Google Calendar, iCloud, Fastmail and Proton each publish a private calendar
as one file at a secret address. Nothing here signs in anywhere: whoever has
the address can read the calendar, so the address is handled like a key and
never logged or put in an error message.
"""
