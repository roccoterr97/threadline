"""Tuning values for collecting messages from LinkedIn and the mailbox.

Nothing here is deployment-specific: these values are the same on the Mac and in
the cloud, so they are code rather than environment variables. Secrets and the
owner's own addresses come from :func:`tracker.shared.config.get_settings`.
"""

from __future__ import annotations

from typing import Final

#: How far back the first collection run looks.
INITIAL_WINDOW_DAYS: Final[int] = 30

#: Extra days re-read on every later run so a slow-arriving message is not missed.
OVERLAP_DAYS: Final[int] = 2

#: Hours before the last successful read of a mailbox that a refresh starts
#: from. Much shorter than the daily overlap because a refresh only catches up
#: on the same day; the next morning's run still re-reads its full overlap.
REFRESH_OVERLAP_HOURS: Final[int] = 6

#: LinkedIn's copy of the messages runs one to two days behind (measured
#: 2026-09-24), so a two-day overlap left no margin. Reading LinkedIn costs the
#: same whatever the window, because the whole archive is fetched anyway.
LINKEDIN_OVERLAP_DAYS: Final[int] = 14

#: Rows requested per page when reading a source that paginates.
SOURCE_PAGE_SIZE: Final[int] = 100

#: Rows written per call when upserting into the database.
DATABASE_BATCH_SIZE: Final[int] = 200

#: Seconds a single request to a message source may take.
HTTP_TIMEOUT_SECONDS: Final[float] = 30.0

# --- LinkedIn ---------------------------------------------------------------

#: Member Data Portability endpoint holding the member's own message archive.
LINKEDIN_SNAPSHOT_URL: Final[str] = "https://api.linkedin.com/rest/memberSnapshotData"

#: Value of the ``Linkedin-Version`` header the snapshot endpoint expects.
LINKEDIN_API_VERSION: Final[str] = "202312"

#: Snapshot domain holding the message archive.
LINKEDIN_INBOX_DOMAIN: Final[str] = "INBOX"

#: LinkedIn's own page unit for the snapshot endpoint. It is not a row count:
#: one page answers with roughly 700 to 1,300 message rows.
LINKEDIN_PAGE_SIZE: Final[int] = 10

#: Most pages a single run will read before giving up, so a paging fault cannot
#: turn into an endless loop. At ~1,000 rows a page this covers 500,000 messages.
LINKEDIN_MAX_PAGES: Final[int] = 500

#: Words that mark a snapshot row as a sponsored message or an InMail advert.
#: A folder's words are compared case-insensitively: a word matches when it
#: equals a marker or begins with one. LinkedIn does not document these values,
#: so ``tracker collect linkedin --show-folders`` prints the real ones.
LINKEDIN_ADVERT_FOLDER_MARKERS: Final[tuple[str, ...]] = (
    "sponsored",
    "inmail",
    "spinmail",
    "advert",
    "promotion",
    "ads",
)

# --- Microsoft Graph --------------------------------------------------------

#: Microsoft's sign-in host; the tenant and the OAuth path follow it.
MICROSOFT_LOGIN_HOST: Final[str] = "https://login.microsoftonline.com"

#: Tenant used unless ``MICROSOFT_TENANT`` says otherwise: personal accounts only.
MICROSOFT_DEFAULT_TENANT: Final[str] = "consumers"

#: Sign-in address for personal Microsoft accounts.
MICROSOFT_LOGIN_URL: Final[str] = f"{MICROSOFT_LOGIN_HOST}/{MICROSOFT_DEFAULT_TENANT}/oauth2/v2.0"

#: Microsoft Graph root.
MICROSOFT_GRAPH_URL: Final[str] = "https://graph.microsoft.com/v1.0"

#: Public application identifier of the open-source ms-365-mcp-server, used
#: unless ``MICROSOFT_CLIENT_ID`` names your own. Replacing it means
#: registering an application and signing in once more.
MICROSOFT_CLIENT_ID: Final[str] = "084a3e9f-a9f4-43f7-89f9-d229cf97853e"

#: Read-only mailbox and calendar permissions, plus the permission to renew
#: without the owner. Adding a permission here needs a new sign-in first: a
#: renewal that asks for one not yet granted is refused.
MICROSOFT_SCOPE: Final[str] = (
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/Calendars.Read "
    "offline_access"
)

#: Messages requested per Graph page.
GRAPH_PAGE_SIZE: Final[int] = 50

#: Pages a single Graph listing will follow before giving up.
GRAPH_MAX_PAGES: Final[int] = 200

#: Graph requests in flight at once. Microsoft allows one application four per
#: mailbox and answers "slow down" beyond that, which costs more than it saves;
#: one below the limit leaves room. Set to 1 to read one request at a time.
GRAPH_CONCURRENT_REQUESTS: Final[int] = 3

#: Well-known mailbox folders never read: they hold nothing to track.
GRAPH_EXCLUDED_FOLDERS: Final[tuple[str, ...]] = (
    "junkemail",
    "deleteditems",
    "drafts",
    "outbox",
)

#: The excluded folder that calendar mail is still read from. Outlook moves a
#: meeting invitation to Deleted Items as soon as it is accepted, so skipping
#: the folder lost every interview the owner said yes to.
GRAPH_CALENDAR_RESCUE_FOLDER: Final[str] = "deleteditems"

#: Graph's type for calendar mail: invitations, updates, cancellations and
#: replies are all ``#microsoft.graph.eventMessage`` or a subtype of it.
GRAPH_CALENDAR_MESSAGE_TYPE: Final[str] = "#microsoft.graph.eventMessage"

#: Seconds between two polls while the owner types the one-time code.
DEVICE_CODE_POLL_SECONDS: Final[float] = 5.0

#: Polls before the sign-in is abandoned — about fifteen minutes.
DEVICE_CODE_MAX_POLLS: Final[int] = 180

# --- Obvious machine mail ---------------------------------------------------

#: Local parts that mark an address as a machine rather than a person. A local
#: part matches when it equals one of these or continues with a separator or a
#: digit, so ``news@`` and ``news-digest@`` match while ``newsom@`` does not.
#: Deliberately excludes ``info``, ``hello`` and ``contact``: a founder writing
#: from one of those is exactly the conversation Threadline exists for.
MACHINE_SENDER_PREFIXES: Final[tuple[str, ...]] = (
    "no-reply",
    "noreply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "notification",
    "newsletter",
    "news",
    "mailer",
    "mailing",
    "bounce",
    "postmaster",
    "automated",
    "auto-confirm",
    "alert",
    "billing",
    "invoice",
    "receipt",
    "marketing",
    "digest",
)

#: Characters that may follow a machine prefix inside a local part.
MACHINE_PREFIX_SEPARATORS: Final[str] = "-_.+"

#: Sending domains whose mail is never a human conversation to track.
MACHINE_SENDER_DOMAINS: Final[tuple[str, ...]] = (
    "linkedin.com",
    "e.linkedin.com",
    "bounce.linkedin.com",
    "facebookmail.com",
    "mail.instagram.com",
    "twitter.com",
    "x.com",
)

#: Header that only bulk senders set.
LIST_UNSUBSCRIBE_HEADER: Final[str] = "List-Unsubscribe"

#: Marks a thread with more than one other participant, so the dashboard shows
#: at a glance that it is not a one-to-one conversation.
GROUP_SUBJECT_PREFIX: Final[str] = "[group]"

#: Systems that send on behalf of many companies or people from one address:
#: e-signature services and shared calendars always do; a system from the rule
#: pack does when it writes from a no-reply address (for a job search: Ashby,
#: Greenhouse, Workable, Lever),
#: while a recruiter's own address on it (``anna.lee@acme.teamtailor-mail.com``)
#: is still that recruiter. For a shared sender the address says nothing about
#: who is writing, so the collector looks behind it (see
#: :mod:`tracker.domain.relay`). Measured on 2026-09-21: 22 threads from about
#: fifteen companies filed under one Ashby "person".
ALWAYS_SHARED_SENDER_DOMAINS: Final[tuple[str, ...]] = (
    "docusign.net",
    "docusign.com",
    "calendar.google.com",
)

#: Single shared addresses on a domain that is otherwise not a relay.
RELAY_SENDER_ADDRESSES: Final[frozenset[str]] = frozenset({"calendar-notification@google.com"})

#: Joins a shared address and a company into one synthetic identifier, such as
#: ``no-reply@ashbyhq.com#northwind ai``. Never part of a real address.
RELAY_IDENTITY_SEPARATOR: Final[str] = "#"

#: Display names that name a shared system rather than the company behind it,
#: whatever the owner tracks. A rule pack adds its own (hiring systems for a job
#: search: see ``profile/presets/job_search.toml``).
RELAY_PLATFORM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "docusign",
        "google calendar",
        "no reply",
        "noreply",
    }
)

#: Local part standing in for every machine address of one company's own
#: domain, so ``notification@`` and ``notifications@acmecareers.example`` are one
#: company record rather than two.
COMPANY_SYSTEM_LOCAL_PART: Final[str] = "no-reply"

#: Suffix e-signature services add to the requester's name ("… via Docusign").
RELAY_VIA_MARKER: Final[str] = " via "

#: A company name read from a subject longer than this is a sentence, not a name.
RELAY_MAX_COMPANY_WORDS: Final[int] = 5

#: How far back and ahead the calendar is read. Meetings move, so the whole
#: range is read again on every run rather than from the last run.
CALENDAR_PAST_DAYS: Final[int] = 30
CALENDAR_FUTURE_DAYS: Final[int] = 60

#: Fields asked for per calendar event. Deliberately no ``body``: Threadline
#: writes a meeting's description itself from these, and never reads the one
#: the organiser typed.
CALENDAR_FIELDS: Final[str] = (
    "id,iCalUId,subject,start,end,organizer,attendees,isCancelled,isOrganizer,"
    "responseStatus,createdDateTime,lastModifiedDateTime"
)

#: Asks Graph to give every event time in UTC.
UTC_TIME_PREFERENCE: Final[str] = 'outlook.timezone="UTC"'

#: Words that make a lone entry the owner's preparation, never the meeting.
OWN_MEETING_EXCLUDED_WORDS: Final[frozenset[str]] = frozenset(
    {"prep", "prepa", "prepare", "preparation", "preparazione"}
)

#: Words dropped from such an entry's title to leave the company it names:
#: the kind of meeting and the joining words around the names.
OWN_MEETING_FILLER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "and",
        "avec",
        "between",
        "call",
        "chat",
        "con",
        "de",
        "di",
        "e",
        "et",
        "final",
        "first",
        "for",
        "meeting",
        "online",
        "phone",
        "round",
        "second",
        "video",
        "with",
        "x",
    }
)

#: Identifier prefix for a company named only by an entry in the owner's own
#: calendar. Joined to the company with ``RELAY_IDENTITY_SEPARATOR``; it is never
#: an address and is never mined for a name or a domain.
OWN_MEETING_IDENTIFIER_PREFIX: Final[str] = "own-calendar"
