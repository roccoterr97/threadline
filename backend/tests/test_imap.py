"""The IMAP reader: parsing, threading, folders, retries and the read-only promise.

Everything runs against :class:`tests.imap_world.FakeImapServer`; no socket is
ever opened and every message is made up.
"""

from __future__ import annotations

import asyncio
import imaplib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from pydantic import SecretStr

from tests.imap_world import (
    APP_PASSWORD,
    GMAIL_ACCOUNT,
    OWNER,
    SENT,
    FakeImapServer,
    StoredMessage,
    body_fetches,
    examines,
    mail,
    session_on,
    writes_sent,
)
from tracker.domain.mail import MailMessage
from tracker.infrastructure.imap import reader
from tracker.infrastructure.imap.html_text import html_to_text
from tracker.infrastructure.imap.parser import extract_body, parse_fetch, parse_headers
from tracker.infrastructure.imap.reader import ImapMailbox, find_sent_folder, imap_date
from tracker.infrastructure.imap.session import Answer, Folder, ImapClient, ImapSession, quote
from tracker.infrastructure.imap.threads import ThreadFacts, thread_keys
from tracker.shared.concurrency import gather_all
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS
from tracker.shared.errors import MailboxPasswordError, SourceUnavailableError

SINCE = datetime(2026, 9, 10, tzinfo=UTC)
ELODIE = "Élodie Martin <elodie@startup.example>"


def at(day: int, month: int = 9) -> datetime:
    """A made-up moment in 2026."""
    return datetime(2026, month, day, 9, 30, tzinfo=UTC)


def gmail_server(*, gmail: bool = True) -> FakeImapServer:
    """A mailbox with a newsletter, a real conversation and older mail."""
    inbox = [
        StoredMessage(
            1,
            mail(
                sender="Digest <news@digest.example>",
                subject="This week's digest",
                sent=at(15),
                message_id="<n1@digest.example>",
                unsubscribe=True,
            ),
            at(15),
            thread="100",
            gmail_id="1001",
        ),
        StoredMessage(
            2,
            mail(
                sender=ELODIE,
                subject="Coffee next week?",
                sent=at(16),
                message_id="<c2@startup.example>",
                references="<c0@startup.example>",
                in_reply_to="<c0@startup.example>",
            ),
            at(16),
            thread="200",
            gmail_id="2002",
        ),
        StoredMessage(
            3,
            mail(sender=ELODIE, subject="Old news", sent=at(1), message_id="<o@startup.example>"),
            at(1),
            thread="300",
            gmail_id="3003",
        ),
        StoredMessage(
            4,
            mail(
                sender=ELODIE,
                subject="Coffee next week?",
                sent=at(20, 8),
                message_id="<c0@startup.example>",
            ),
            at(20, 8),
            thread="200",
            gmail_id="2000",
        ),
    ]
    sent = [
        StoredMessage(
            1,
            mail(
                sender=f"Sam <{OWNER}>",
                to=ELODIE,
                subject="Re: Coffee next week?",
                sent=at(17),
                message_id="<r1@gmail.example>",
                references="<c0@startup.example> <c2@startup.example>",
                in_reply_to="<c2@startup.example>",
            ),
            at(17),
            thread="200",
            gmail_id="2003",
        ),
    ]
    return FakeImapServer(
        folders={"INBOX": inbox, SENT: sent},
        attributes={SENT: "\\HasNoChildren \\Sent"},
        gmail=gmail,
    )


def read_window(server: FakeImapServer) -> list[MailMessage]:
    """Open the mailbox and run the metadata pass."""

    async def run() -> list[MailMessage]:
        async with ImapMailbox(session_on(server)) as mailbox:
            return await mailbox.list_messages_since(SINCE)

    return asyncio.run(run())


# --- Parsing ------------------------------------------------------------------


def test_a_multipart_message_gives_its_plain_text_part() -> None:
    raw = mail(
        sender=ELODIE,
        subject="Hi",
        sent=at(16),
        message_id="<a@x>",
        body="Plain words.",
        html="<p>HTML words.</p>",
    )

    assert extract_body(raw, 1000) == "Plain words."


def test_an_html_only_message_is_turned_into_text() -> None:
    message = EmailMessage()
    message["Subject"] = "Hi"
    message.set_content(
        "<html><head><style>p{}</style></head><body><p>Hello&nbsp;Sam</p>"
        "<script>alert(1)</script><div>See you &amp; bye</div></body></html>",
        subtype="html",
    )

    assert extract_body(message.as_bytes(), 1000) == "Hello Sam\n\nSee you & bye"


def test_a_latin_charset_is_decoded() -> None:
    raw = (
        b"Content-Type: text/plain; charset=iso-8859-1\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n\r\nCaf\xe9 cr\xe8me"
    )

    assert extract_body(raw, 1000) == "Café crème"


def test_an_unknown_charset_falls_back_without_failing() -> None:
    raw = b"Content-Type: text/plain; charset=x-made-up\r\n\r\nHello \xff there"

    assert extract_body(raw, 1000) == "Hello � there"


def test_attachments_are_never_read_as_the_body() -> None:
    message = EmailMessage()
    message.set_content("The real note.")
    message.add_attachment(
        b"secret spreadsheet", maintype="text", subtype="plain", filename="notes.txt"
    )

    assert extract_body(message.as_bytes(), 1000) == "The real note."


def test_a_huge_body_is_cut_to_the_limit() -> None:
    raw = mail(sender=ELODIE, subject="Long", sent=at(16), message_id="<l@x>", body="a" * 5000)

    assert len(extract_body(raw, 100)) == 100


def test_encoded_headers_are_decoded_and_addresses_lower_cased() -> None:
    raw = (
        b"From: =?utf-8?q?=C3=89lodie_Martin?= <Elodie@Startup.Example>\r\n"
        b'To: "Rivera, Sam" <sam@x.example>, other@y.example\r\n'
        b"Subject: =?iso-8859-1?q?Caf=E9?= next\r\n\tweek\r\n"
        b"Date: Wed, 16 Sep 2026 11:30:00 +0200\r\n"
        b"List-Unsubscribe: <https://x.example/u>\r\n\r\n"
    )

    facts = parse_headers(raw)

    assert facts.sender == ("elodie@startup.example", "Élodie Martin")
    assert facts.recipients == (("sam@x.example", "Rivera, Sam"), ("other@y.example", ""))
    assert facts.subject == "Café next week"
    assert facts.sent_at == datetime(2026, 9, 16, 9, 30, tzinfo=UTC)
    assert facts.has_list_unsubscribe


def test_a_broken_date_and_bytes_never_fail_the_read() -> None:
    facts = parse_headers(b"From: x@y.example\r\nSubject: bad \xff byte\r\nDate: nonsense\r\n\r\n")

    assert facts.sent_at is None
    assert facts.subject == "bad � byte"


def test_a_fetch_answer_with_items_after_the_literal_is_read() -> None:
    data: list[object] = [
        (b'1 (INTERNALDATE "16-Sep-2026 09:30:00 +0000" BODY[] {5}', b"hello"),
        b" UID 42 X-GM-THRID 77)",
    ]

    [record] = parse_fetch(data)

    assert (record.uid, record.gmail_thread_id, record.literal) == (42, "77", b"hello")
    assert record.internal_date == at(16)


def test_html_to_text_keeps_paragraphs_apart() -> None:
    assert html_to_text("<p>One</p><p>Two<br>Three</p>") == "One\n\nTwo\nThree"


# --- Threading ----------------------------------------------------------------


def facts(
    message_id: str, *, references: tuple[str, ...] = (), reply_to: str = "", subject: str = "Hi"
) -> ThreadFacts:
    """Made-up threading headers."""
    return ThreadFacts(message_id, reply_to, references, subject, stand_in=message_id)


def test_a_references_chain_is_one_thread_named_after_its_first_message() -> None:
    keys = thread_keys(
        [facts("<a>"), facts("<b>", references=("<a>",)), facts("<c>", references=("<a>", "<b>"))]
    )

    assert keys == ["mid:<a>", "mid:<a>", "mid:<a>"]


def test_a_reply_with_only_in_reply_to_follows_its_parent() -> None:
    keys = thread_keys([facts("<a>"), facts("<b>", reply_to="<a>"), facts("<c>", reply_to="<b>")])

    assert keys == ["mid:<a>", "mid:<a>", "mid:<a>"]


def test_a_reply_that_lost_its_headers_joins_by_subject() -> None:
    keys = thread_keys([facts("<a>", subject="Coffee?"), facts("<b>", subject="RE: Coffee?")])

    assert keys == ["mid:<a>", "mid:<a>"]


def test_two_unrelated_messages_with_one_subject_stay_apart() -> None:
    keys = thread_keys([facts("<a>", subject="Hello"), facts("<b>", subject="Hello")])

    assert keys == ["mid:<a>", "mid:<b>"]


# --- Folders ------------------------------------------------------------------


def test_the_sent_folder_is_found_by_its_marker_in_any_language() -> None:
    folders = [
        Folder("INBOX", frozenset()),
        Folder("[Gmail]/Gesendet", frozenset({"\\hasnochildren", "\\sent"})),
        Folder("Sent", frozenset()),
    ]

    assert find_sent_folder(folders) == "[Gmail]/Gesendet"


def test_the_sent_folder_is_found_by_name_without_a_marker() -> None:
    folders = [Folder("INBOX", frozenset()), Folder("Sent Messages", frozenset())]

    assert find_sent_folder(folders) == "Sent Messages"


def test_no_sent_folder_is_reported_as_none() -> None:
    folders = [Folder("INBOX", frozenset()), Folder("[Gmail]", frozenset({"\\noselect"}))]

    assert find_sent_folder(folders) is None


def test_a_mailbox_without_a_sent_folder_still_reads_the_inbox() -> None:
    server = gmail_server()
    server.folders.pop(SENT)

    messages = read_window(server)

    assert {message.subject for message in messages} == {"This week's digest", "Coffee next week?"}


# --- The reader ---------------------------------------------------------------


def test_gmail_threads_use_gmails_own_thread_identifier() -> None:
    messages = read_window(gmail_server())

    by_subject = {message.subject: message for message in messages}
    assert by_subject["Coffee next week?"].conversation_id == "gmail-200"
    assert by_subject["Re: Coffee next week?"].conversation_id == "gmail-200"
    assert by_subject["This week's digest"].conversation_id == "gmail-100"


def test_other_servers_thread_by_the_references_chain() -> None:
    messages = read_window(gmail_server(gmail=False))

    by_subject = {message.subject: message for message in messages}
    assert (
        by_subject["Coffee next week?"].conversation_id
        == by_subject["Re: Coffee next week?"].conversation_id
    )
    assert by_subject["Coffee next week?"].conversation_id.startswith("imap-")
    assert "startup" not in by_subject["Coffee next week?"].conversation_id


def test_only_messages_inside_the_window_are_read() -> None:
    subjects = {message.subject for message in read_window(gmail_server())}

    assert "Old news" not in subjects


def test_a_server_behind_utc_still_finds_mail_from_the_windows_first_hours() -> None:
    since = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
    early = datetime(2026, 9, 11, 3, 0, tzinfo=UTC)
    before = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)
    inbox = [
        StoredMessage(
            uid,
            mail(sender=ELODIE, subject=subject, sent=moment, message_id=f"<{uid}@x.example>"),
            moment,
        )
        for uid, subject, moment in ((1, "Too early", before), (2, "Early hours", early))
    ]
    # On the server's clock (UTC-5) the early message arrived on 10 September.
    server = FakeImapServer(folders={"INBOX": inbox}, gmail=False, utc_offset=timedelta(hours=-5))

    async def run() -> list[MailMessage]:
        async with ImapMailbox(session_on(server)) as mailbox:
            return await mailbox.list_messages_since(since)

    assert [message.subject for message in asyncio.run(run())] == ["Early hours"]
    assert ("UID", "SEARCH", "SINCE", "10-Sep-2026") in server.log


def test_a_folder_with_too_many_messages_gives_its_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reader, "IMAP_MAX_MESSAGES_PER_FOLDER", 1)

    subjects = {message.subject for message in read_window(gmail_server())}

    assert subjects == {"Coffee next week?", "Re: Coffee next week?"}


def test_sent_messages_are_the_owners_and_carry_the_headers_needed() -> None:
    messages = read_window(gmail_server())

    reply = next(message for message in messages if message.subject.startswith("Re:"))
    digest = next(message for message in messages if message.subject == "This week's digest")
    assert reply.from_owner
    assert reply.recipients == (("elodie@startup.example", "Élodie Martin"),)
    assert digest.has_list_unsubscribe
    assert not digest.from_owner
    assert digest.body is None


@pytest.mark.parametrize("gmail", [True, False])
def test_a_whole_thread_and_its_bodies_can_be_read(gmail: bool) -> None:
    server = gmail_server(gmail=gmail)

    async def run() -> tuple[list[MailMessage], str]:
        async with ImapMailbox(session_on(server)) as mailbox:
            recent = await mailbox.list_messages_since(SINCE)
            thread = next(m.conversation_id for m in recent if m.subject.startswith("Re:"))
            whole = await mailbox.list_thread(thread)
            return whole, await mailbox.fetch_body(whole[0].message_id)

    whole, body = asyncio.run(run())

    assert len(whole) == 3
    assert body == "Made-up body text."


#: Seconds a watched command takes, so two commands sent together would overlap.
_COMMAND_SECONDS = 0.002


@dataclass
class WatchedImapServer(FakeImapServer):
    """A fake server that notices two commands on the connection at once."""

    busy: int = 0
    overlaps: int = 0

    def uid(self, command: str, *args: str) -> Answer:
        """Answer as usual, counting any command that arrives during another."""
        self.busy += 1
        self.overlaps += self.busy > 1
        time.sleep(_COMMAND_SECONDS)
        try:
            return super().uid(command, *args)
        finally:
            self.busy -= 1


def test_many_requests_at_once_take_turns_on_the_one_connection() -> None:
    plain = gmail_server()
    server = WatchedImapServer(folders=plain.folders, attributes=plain.attributes)

    async def run() -> tuple[list[str], list[str]]:
        async with ImapMailbox(session_on(server)) as mailbox:
            recent = await mailbox.list_messages_since(SINCE)
            one_by_one = [await mailbox.fetch_body(m.message_id) for m in recent]
            together = await gather_all(mailbox.fetch_body(m.message_id) for m in recent)
            await gather_all(mailbox.list_thread(m.conversation_id) for m in recent)
            return one_by_one, together

    one_by_one, together = asyncio.run(run())

    assert len(together) > 1
    assert together == one_by_one
    assert server.overlaps == 0


def test_nothing_is_ever_marked_moved_or_changed() -> None:
    server = gmail_server()

    async def run() -> None:
        async with ImapMailbox(session_on(server)) as mailbox:
            for message in await mailbox.list_messages_since(SINCE):
                await mailbox.list_thread(message.conversation_id)
                await mailbox.fetch_body(message.message_id)

    asyncio.run(run())

    assert writes_sent(server) == []
    assert any(entry[:2] == ("UID", "FETCH") for entry in server.log)
    assert all(entry[2] == "readonly" for entry in server.log if entry[0] == "SELECT")


# --- Bodies, a thread at a time -----------------------------------------------

#: Gmail's thread numbers on the made-up server of :func:`two_threads`.
INBOX_ONLY, ANSWERED = "500", "600"


def note(uid: int, name: str, thread: str, day: int, *, sent: bool = False) -> StoredMessage:
    """A message whose text names it, so a body given to the wrong message shows."""
    return StoredMessage(
        uid,
        mail(
            sender=f"Sam <{OWNER}>" if sent else ELODIE,
            to=ELODIE if sent else OWNER,
            subject="Coffee next week?",
            sent=at(day),
            message_id=f"<{name}@startup.example>",
            body=f"Text of {name}.",
        ),
        at(day),
        thread=thread,
        gmail_id=f"{thread}{day}",
    )


def two_threads() -> FakeImapServer:
    """A thread of three inbox messages, and one with two messages in each folder."""
    inbox = [
        note(1, "a1", INBOX_ONLY, 11),
        note(2, "b1", ANSWERED, 12),
        note(3, "a2", INBOX_ONLY, 13),
        note(4, "a3", INBOX_ONLY, 15),
        note(5, "b3", ANSWERED, 16),
    ]
    sent = [note(1, "b2", ANSWERED, 14, sent=True), note(2, "b4", ANSWERED, 17, sent=True)]
    return FakeImapServer(
        folders={"INBOX": inbox, SENT: sent}, attributes={SENT: "\\HasNoChildren \\Sent"}
    )


@dataclass
class BodyRead:
    """What reading one thread's bodies gave, and the commands it cost."""

    bodies: list[str]
    commands: list[tuple[str, ...]]


def read_bodies(
    server: FakeImapServer,
    thread: str,
    *,
    before: Callable[[], None] = lambda: None,
    one_by_one: bool = False,
) -> BodyRead:
    """List the window, then read one thread's bodies, oldest message first.

    ``before`` runs between the two, once the log has been emptied: the place
    to make the server misbehave.
    """

    async def run() -> list[str]:
        async with ImapMailbox(session_on(server)) as mailbox:
            recent = await mailbox.list_messages_since(SINCE)
            wanted = sorted(
                (m for m in recent if m.conversation_id == f"gmail-{thread}"),
                key=lambda m: m.sent_at,
            )
            server.log.clear()
            before()
            if one_by_one:
                return [await mailbox.fetch_body(m.message_id) for m in wanted]
            return await mailbox.fetch_bodies([m.message_id for m in wanted])

    bodies = asyncio.run(run())
    return BodyRead(bodies, [entry for entry in server.log if entry[0] != "LOGOUT"])


def test_the_bodies_of_a_thread_in_one_folder_cost_one_fetch() -> None:
    server = two_threads()

    read = read_bodies(server, INBOX_ONLY)

    assert read.bodies == ["Text of a1.", "Text of a2.", "Text of a3."]
    assert examines(server) == ["INBOX"]
    assert body_fetches(server) == ["1,3,4"]


def test_a_thread_in_the_inbox_and_sent_costs_one_fetch_per_folder() -> None:
    server = two_threads()

    read = read_bodies(server, ANSWERED)

    assert read.bodies == ["Text of b1.", "Text of b2.", "Text of b3.", "Text of b4."]
    # The window's listing left Sent open, so Sent is read first and only the
    # inbox has to be opened.
    assert [entry[:3] for entry in read.commands] == [
        ("UID", "FETCH", "1,2"),
        ("SELECT", '"INBOX"', "readonly"),
        ("UID", "FETCH", "2,5"),
    ]
    assert writes_sent(server) == []


def test_a_folder_that_is_open_is_not_opened_again() -> None:
    server = two_threads()

    read = read_bodies(server, INBOX_ONLY, one_by_one=True)

    assert read.bodies == ["Text of a1.", "Text of a2.", "Text of a3."]
    assert examines(server) == ["INBOX"]
    assert body_fetches(server) == ["1", "3", "4"]


def test_a_dropped_line_opens_the_folder_again_before_reading_on() -> None:
    server = two_threads()

    def drop_the_line() -> None:
        server.drop_next_command = 1

    read = read_bodies(server, ANSWERED, before=drop_the_line)

    assert read.bodies == ["Text of b1.", "Text of b2.", "Text of b3.", "Text of b4."]
    assert [entry[:3] for entry in read.commands] == [
        ("UID", "FETCH", "1,2"),  # the line drops here
        ("CONNECT", "imap.gmail.com", "993"),
        ("LOGIN", OWNER),
        ("SELECT", f'"{SENT}"', "readonly"),
        ("UID", "FETCH", "1,2"),
        ("SELECT", '"INBOX"', "readonly"),
        ("UID", "FETCH", "2,5"),
    ]


def test_a_line_that_drops_again_while_reopening_still_opens_the_folder() -> None:
    server = two_threads()

    def drop_the_line_twice() -> None:
        server.drop_next_command = 2

    read = read_bodies(server, ANSWERED, before=drop_the_line_twice)

    assert read.bodies == ["Text of b1.", "Text of b2.", "Text of b3.", "Text of b4."]
    assert [entry[0] for entry in read.commands] == [
        "UID",  # the line drops here
        "CONNECT",
        "LOGIN",
        "SELECT",  # and here again
        "CONNECT",
        "LOGIN",
        "SELECT",
        "UID",
        "SELECT",
        "UID",
    ]
    assert examines(server) == [SENT, SENT, "INBOX"]


def test_bodies_keep_their_message_when_the_server_answers_in_another_order() -> None:
    server = two_threads()
    server.answers_newest_first = True

    read = read_bodies(server, ANSWERED)

    assert read.bodies == ["Text of b1.", "Text of b2.", "Text of b3.", "Text of b4."]


def test_bodies_come_back_in_the_order_asked_whatever_the_folders() -> None:
    server = two_threads()

    async def run() -> list[str]:
        async with ImapMailbox(session_on(server)) as mailbox:
            recent = await mailbox.list_messages_since(SINCE)
            newest_first = sorted(recent, key=lambda m: m.sent_at, reverse=True)
            return await mailbox.fetch_bodies([m.message_id for m in newest_first])

    assert asyncio.run(run()) == [
        "Text of b4.",
        "Text of b3.",
        "Text of a3.",
        "Text of b2.",
        "Text of a2.",
        "Text of b1.",
        "Text of a1.",
    ]
    assert body_fetches(server) == ["1,2", "1,2,3,4,5"]


def test_a_message_that_vanished_reads_as_empty_and_the_others_keep_their_text() -> None:
    server = two_threads()

    def delete_the_second() -> None:
        server.folders["INBOX"] = [m for m in server.folders["INBOX"] if m.uid != 3]

    read = read_bodies(server, INBOX_ONLY, before=delete_the_second)

    assert read.bodies == ["Text of a1.", "", "Text of a3."]


def test_an_identifier_never_seen_reads_as_empty_without_asking_the_server() -> None:
    server = two_threads()

    async def run() -> list[str]:
        async with ImapMailbox(session_on(server)) as mailbox:
            return await mailbox.fetch_bodies(["gmail-never-seen"])

    assert asyncio.run(run()) == [""]
    assert body_fetches(server) == []


@dataclass
class ChattyImapServer(FakeImapServer):
    """A fake server that reports a flag change at the end of every FETCH answer."""

    def uid(self, command: str, *args: str) -> Answer:
        """Answer as usual, then add a line about the first message's flags."""
        status, data = super().uid(command, *args)
        if command != "FETCH":
            return status, data
        first = args[0].split(",")[0]
        return status, [*data, f"9 (UID {first} FLAGS (\\Seen))".encode()]


def test_a_line_about_flags_is_never_taken_for_a_body() -> None:
    plain = two_threads()
    server = ChattyImapServer(folders=plain.folders, attributes=plain.attributes)

    read = read_bodies(server, INBOX_ONLY)

    assert read.bodies == ["Text of a1.", "Text of a2.", "Text of a3."]


def test_a_long_thread_is_fetched_a_bounded_number_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reader, "IMAP_BODY_BATCH_SIZE", 2)
    server = two_threads()

    read = read_bodies(server, INBOX_ONLY)

    assert read.bodies == ["Text of a1.", "Text of a2.", "Text of a3."]
    assert body_fetches(server) == ["1,3", "4"]


def test_the_survey_counts_the_inbox_window_and_names_the_sent_folder() -> None:
    async def run() -> tuple[int, str | None]:
        async with ImapMailbox(session_on(gmail_server())) as mailbox:
            survey = await mailbox.survey(SINCE)
            return survey.inbox_messages, survey.sent_folder

    assert asyncio.run(run()) == (2, SENT)


def test_imap_dates_do_not_depend_on_the_machine_language() -> None:
    assert imap_date(datetime(2026, 9, 3, 23, 0, tzinfo=UTC)) == "3-Sep-2026"


def test_a_quoted_value_can_never_end_the_command() -> None:
    assert quote('a"b\\c\r\nSTORE') == '"a\\"b\\\\cSTORE"'


# --- Sign-in and retries ------------------------------------------------------


def test_a_refused_app_password_is_a_password_error_and_is_not_retried() -> None:
    server = gmail_server()

    with pytest.raises(MailboxPasswordError, match="Google refused the app password"):
        session_on(server, password="wrong").open()

    assert server.connections == 1


def test_a_dropped_line_is_reopened_and_the_command_tried_again() -> None:
    server = gmail_server()
    server.drop_next_command = 1

    messages = read_window(server)

    assert messages
    assert server.connections == 2


def test_a_server_that_never_answers_is_unavailable() -> None:
    attempts: list[str] = []

    def refuse(host: str, port: int, timeout: float) -> FakeImapServer:
        attempts.append(host)
        raise ConnectionRefusedError(host)

    session = ImapSession(
        GMAIL_ACCOUNT, SecretStr(APP_PASSWORD), connect=refuse, sleep=lambda _seconds: None
    )

    with pytest.raises(SourceUnavailableError, match="Gmail did not answer"):
        session.open()
    assert len(attempts) == SOURCE_REQUEST_ATTEMPTS


def test_a_greeting_that_is_not_a_mail_servers_is_unavailable_not_a_crash() -> None:
    attempts: list[str] = []

    def greet_badly(host: str, port: int, timeout: float) -> FakeImapServer:
        attempts.append(host)
        message = "* BYE too many connections"
        raise imaplib.IMAP4.error(message)

    session = ImapSession(
        GMAIL_ACCOUNT, SecretStr(APP_PASSWORD), connect=greet_badly, sleep=lambda _seconds: None
    )

    with pytest.raises(SourceUnavailableError, match="Gmail did not answer"):
        session.open()
    assert len(attempts) == SOURCE_REQUEST_ATTEMPTS


def test_a_bad_greeting_once_is_tried_again() -> None:
    server = gmail_server()
    greetings = [imaplib.IMAP4.error("* BYE busy")]

    def greet(host: str, port: int, timeout: float) -> ImapClient:
        if greetings:
            raise greetings.pop()
        return server.connect(host, port, timeout)

    session = ImapSession(
        GMAIL_ACCOUNT, SecretStr(APP_PASSWORD), connect=greet, sleep=lambda _seconds: None
    )

    session.open()

    assert server.connections == 1


def test_a_missing_folder_is_reported_not_crashed() -> None:
    session = session_on(gmail_server())
    session.open()

    with pytest.raises(SourceUnavailableError):
        session.examine("Nowhere")


def test_a_refused_folder_leaves_none_open() -> None:
    server = gmail_server()
    session = session_on(server)
    session.open()
    session.examine("INBOX")

    with pytest.raises(SourceUnavailableError):
        session.examine("Nowhere")
    session.examine("INBOX")

    assert examines(server) == ["INBOX", "Nowhere", "INBOX"]
    assert session.search("SINCE", imap_date(SINCE)) == [1, 2]
