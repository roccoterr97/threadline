"""Collection commands: read the sources, sign in to Microsoft, list people.

Every handler does the same three things and nothing else: build the service,
call one method, print the result. Anything that goes wrong raises a
:class:`~tracker.shared.errors.TrackerError`, which the entry point turns into
one clean line and exit status 1.

``collect all --record`` is the exception the daily run is built on: a source
that fails is printed and recorded as that step's result, and the command still
ends normally so the run carries on with the sources that worked.
``people tidy`` does the same for the two commands it folds into one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, tzinfo
from typing import Annotated, Final
from uuid import UUID

import typer

from tracker.cli.commands._parts import attempt
from tracker.domain.enums import Channel, RunStep
from tracker.domain.rules import RulePack
from tracker.infrastructure.database import create_database_client
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.repositories import Repositories, build_repositories
from tracker.services.collection.all_sources import (
    AllSourcesCollector,
    Source,
    SourceOutcome,
    record_outcomes,
)
from tracker.services.collection.calendar_collector import CalendarCollector
from tracker.services.collection.email_collector import EmailCollector
from tracker.services.collection.linkedin_collector import LinkedInCollector
from tracker.services.collection.models import CollectionReport
from tracker.services.collection.window import refresh_since
from tracker.services.identity.directory import DirectoryEntry, PeopleDirectory
from tracker.services.identity.linker import PeopleLinker
from tracker.services.identity.merge import PersonMerger
from tracker.services.identity.naming import AddressNamer
from tracker.services.identity.relay_repair import RelayUntangler
from tracker.services.profile.loader import load_profile
from tracker.services.runs.run_recorder import RunRecorder, unconfigured_steps
from tracker.shared.clock import Clock, SystemClock
from tracker.shared.config import Settings, get_settings
from tracker.shared.errors import TrackerError, ValidationFailedError

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "collect"

#: Date format the ``--since`` option accepts.
SINCE_FORMAT: Final[str] = "%Y-%m-%d"

collect_app = typer.Typer(
    help="Collect messages from LinkedIn and your mailboxes.",
    no_args_is_help=True,
)

microsoft_app = typer.Typer(
    help="Sign in to the Microsoft mailbox, once.",
    no_args_is_help=True,
)

people_app = typer.Typer(
    help="Look at the people the collectors have found.",
    no_args_is_help=True,
)

SinceOption = Annotated[
    str | None,
    typer.Option(
        "--since",
        help="Collect from this day instead of the usual window (YYYY-MM-DD).",
        show_default=False,
    ),
]

RefreshOption = Annotated[
    bool,
    typer.Option(
        "--refresh",
        help=(
            "Read only what is new since the mailboxes were last read successfully; "
            "with --record, record into the refresh that is open."
        ),
    ),
]

RecordOption = Annotated[
    bool,
    typer.Option(
        "--record",
        help="Record each source's result as its step of the run, and carry on past a failure.",
    ),
]

RunOption = Annotated[
    UUID | None,
    typer.Option("--run", help="With --record: record into this run, not the one still open."),
]

ShowFoldersOption = Annotated[
    bool,
    typer.Option(
        "--show-folders",
        help="Also print the distinct LinkedIn folder values, to check the advert rule.",
    ),
]


def register(cli: typer.Typer) -> None:
    """Attach the collection commands to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.add_typer(collect_app, name="collect", rich_help_panel=HELP_PANEL)
    cli.add_typer(microsoft_app, name="microsoft", rich_help_panel=HELP_PANEL)
    cli.add_typer(people_app, name="people", rich_help_panel=HELP_PANEL)


@collect_app.command("linkedin")
def collect_linkedin(since: SinceOption = None, show_folders: ShowFoldersOption = False) -> None:
    """Read the LinkedIn archive and store the recent conversations."""
    settings, repositories = _wiring()
    clock = SystemClock(settings.owner_zone)
    collector = LinkedInCollector(repositories, settings, clock, _rules(repositories))
    report = collector.collect(since=_parse_since(since, settings.owner_zone))
    _print(report)
    if show_folders:
        typer.echo(f"folders seen: {', '.join(report.folders_seen) or 'none'}")


@collect_app.command("email")
def collect_email(since: SinceOption = None, refresh: RefreshOption = False) -> None:
    """Read every mailbox you set up (Outlook, Gmail…) and store what is worth keeping."""
    if refresh and since is not None:
        message = "--refresh and --since cannot be used together"
        raise ValidationFailedError(message)
    settings, repositories = _wiring()
    clock = SystemClock(settings.owner_zone)
    collector = EmailCollector(repositories, settings, clock, _rules(repositories))
    start = _parse_since(since, settings.owner_zone)
    _print(collector.collect(since=_mail_start(repositories, start, refresh=refresh)))


@collect_app.command("calendar")
def collect_calendar() -> None:
    """Read the Outlook calendar and store the meetings with other people."""
    settings, repositories = _wiring()
    clock = SystemClock(settings.owner_zone)
    _print(CalendarCollector(repositories, settings, clock, _rules(repositories)).collect())


@collect_app.command("all")
def collect_all(
    since: SinceOption = None,
    refresh: RefreshOption = False,
    record: RecordOption = False,
    run: RunOption = None,
) -> None:
    """Read every source at the same time, then store them one after the other."""
    if refresh and since is not None:
        message = "--refresh and --since cannot be used together"
        raise ValidationFailedError(message)
    settings, repositories = _wiring()
    clock = SystemClock(settings.owner_zone)
    recorder = RunRecorder(repositories, clock, unconfigured_steps(settings))
    # Looked up before anything is read, so a run that does not exist is
    # reported straight away rather than after the whole collection.
    target = recorder.resolve(run, refresh=refresh) if record else None
    start = _parse_since(since, settings.owner_zone)
    mail_start = _mail_start(repositories, start, refresh=refresh)
    sources = _sources(repositories, settings, clock, start, mail_start)
    outcomes = AllSourcesCollector(sources).collect()
    _print_outcomes(outcomes)
    if target is None:
        _raise_first_failure(outcomes)
        return
    record_outcomes(recorder, target.id, outcomes)
    typer.echo("steps recorded")


@microsoft_app.command("login")
def microsoft_login() -> None:
    """Sign in to the mailbox once; the key then renews itself."""
    settings, repositories = _wiring()
    store = SecretStore(repositories.app_secrets, settings.token_encryption_key, SystemClock())
    asyncio.run(_sign_in(store, settings))
    typer.echo("signed in · the mailbox and calendar key is stored encrypted in the database")


@microsoft_app.command("forget")
def microsoft_forget() -> None:
    """Remove the stored mailbox key, so the next run needs a new sign-in."""
    settings, repositories = _wiring()
    store = SecretStore(repositories.app_secrets, settings.token_encryption_key, SystemClock())
    removed = store.delete_secret(MICROSOFT_REFRESH_TOKEN)
    typer.echo("mailbox key removed" if removed else "there was no mailbox key to remove")


@people_app.command("list")
def people_list() -> None:
    """Show everybody the collectors have found, most recent first."""
    _, repositories = _wiring()
    entries = PeopleDirectory(repositories).list_people()
    if not entries:
        typer.echo("no people collected yet")
        return
    for entry in entries:
        typer.echo(_person_line(entry))
    typer.echo(f"{len(entries)} people")


@people_app.command("merge")
def people_merge() -> None:
    """Join the records you have confirmed are one person.

    The matcher only ever asks; answering "yes" in the review list is what
    settles it, and this applies those answers.
    """
    _, repositories = _wiring()
    report = PersonMerger(repositories).apply_answers()
    if report.questions_closed:
        typer.echo(
            f"questions closed because their two records are already one: {report.questions_closed}"
        )
    if not report.merged and not report.skipped:
        typer.echo("nothing to merge - no confirmed pairs are waiting")
        return
    typer.echo(
        f"people merged: {report.merged} "
        f"({report.identities_moved} addresses and profiles, "
        f"{report.conversations_moved} conversations moved)"
    )
    if report.skipped:
        typer.echo(f"already done: {report.skipped}")


@people_app.command("link")
def people_link() -> None:
    """Ask about records that look like one person or one opportunity.

    Nothing is joined here: every pair becomes a question in the review list,
    and "people merge" acts on the answers. Afterwards, anybody still shown as
    an address that plainly spells a name is shown by that name.
    """
    _, repositories = _wiring()
    rules = _rules(repositories)
    report = PeopleLinker(repositories, rules).link()
    named = AddressNamer(repositories, rules).name_all()
    if named:
        typer.echo(f"people given the name their address spells: {named}")
    if report.joined:
        typer.echo(f"company lines joined to their one contact: {report.joined}")
    if not report.asked:
        typer.echo("nothing new to ask - no new likely pairs")
    else:
        typer.echo(f"questions added to the review list: {report.asked}")
    if report.already_asked:
        typer.echo(f"already asked before: {report.already_asked}")


@people_app.command("tidy")
def people_tidy() -> None:
    """Act on your "same person" answers, then ask about new likely pairs.

    The daily run's two steps after collecting, as one command: "people merge",
    then "people link", each printing what it prints on its own. If one fails,
    its code is printed and the other still runs.
    """
    attempt("people merge", people_merge)
    attempt("people link", people_link)


@people_app.command("untangle")
def people_untangle() -> None:
    """Split up records that were really a shared sender, such as a hiring system.

    One-off repair: afterwards, read the mailbox again with
    "collect email --since" so each released thread finds its real sender.
    """
    _, repositories = _wiring()
    report = RelayUntangler(repositories, _rules(repositories)).untangle()
    if not report.identities_removed and not report.noise_verdicts_reset:
        typer.echo("nothing to untangle - no record is a shared sender")
        return
    typer.echo(
        f"shared senders removed: {report.identities_removed} · "
        f"conversations released: {report.conversations_released} · "
        f"records hidden: {report.people_hidden} · "
        f"people to assess again: {report.people_to_reassess} · "
        f"system threads given back: {report.noise_verdicts_reset}"
    )


async def _sign_in(store: SecretStore, settings: Settings) -> None:
    """Show the one-time code, then wait for the owner to type it.

    Args:
        store: Where the long-lived key is written once sign-in succeeds.
        settings: Names the application and tenant to sign in through.
    """
    async with MicrosoftAuthenticator.for_settings(store, SystemClock(), settings) as authenticator:
        prompt = await authenticator.request_device_code()
        typer.echo(f"1. open {prompt.verification_url}")
        typer.echo(f"2. type the code: {prompt.user_code}")
        typer.echo("3. approve the read-only mailbox and calendar permissions, then wait here")
        await authenticator.wait_for_sign_in(prompt)


def _sources(
    repositories: Repositories,
    settings: Settings,
    clock: Clock,
    start: datetime | None,
    mail_start: datetime | None,
) -> tuple[tuple[Source, ...], ...]:
    """Build the sources of a run, grouped by what may be read at the same time.

    Args:
        repositories: The repository container.
        settings: The process configuration.
        clock: Supplies the current instant.
        start: An explicit start for LinkedIn, or ``None`` for the usual window.
        mail_start: An explicit start for the mailboxes, or ``None``.

    Returns:
        LinkedIn on its own; the mailboxes and the calendar together.
    """
    rules = _rules(repositories)
    linkedin = LinkedInCollector(repositories, settings, clock, rules)
    email = EmailCollector(repositories, settings, clock, rules)
    calendar = CalendarCollector(repositories, settings, clock, rules)
    return (
        (Source(Channel.LINKEDIN, RunStep.COLLECT_LINKEDIN, lambda: linkedin.read(since=start)),),
        # An Outlook mailbox and the calendar renew the same Microsoft key, and
        # each renewal replaces it. Read one after the other, never together.
        (
            Source(Channel.EMAIL, RunStep.COLLECT_EMAIL, lambda: email.read(since=mail_start)),
            Source(Channel.CALENDAR, RunStep.COLLECT_CALENDAR, calendar.read),
        ),
    )


def _mail_start(
    repositories: Repositories, start: datetime | None, *, refresh: bool
) -> datetime | None:
    """Where the mailboxes are read from: a refresh reads only what is new."""
    return refresh_since(repositories, RunStep.COLLECT_EMAIL) if refresh else start


def _print_outcomes(outcomes: Sequence[SourceOutcome]) -> None:
    """Print each source's counts or its failure, then how many were collected."""
    for outcome in outcomes:
        if outcome.failure is not None:
            typer.echo(f"channel: {outcome.source.channel.value}")
            typer.echo(f"failed · code={outcome.failure.code}")
        elif outcome.report is not None:
            _print(outcome.report)
        typer.echo("")
    collected = sum(outcome.succeeded for outcome in outcomes)
    typer.echo(f"sources collected: {collected}")


def _raise_first_failure(outcomes: Sequence[SourceOutcome]) -> None:
    """End a run by hand on the first problem, once every source has been printed.

    Raises:
        TrackerError: The first source's failure, or why it was read only in
            part, when there is one.
    """
    failure: TrackerError | None = next(
        (outcome.problem for outcome in outcomes if outcome.problem is not None), None
    )
    if failure is not None:
        raise failure


def _wiring() -> tuple[Settings, Repositories]:
    """Build the configuration and the repositories a command needs."""
    settings = get_settings()
    return settings, build_repositories(create_database_client(settings))


def _rules(repositories: Repositories) -> RulePack:
    """The owner's collection rules: from their profile file, else their chosen preset."""
    chosen = repositories.app_settings.read_preset()
    return load_profile(chosen_preset=chosen).profile.rules


def _parse_since(value: str | None, zone: tzinfo) -> datetime | None:
    """Read the ``--since`` option.

    Args:
        value: What the owner typed, or ``None``.
        zone: The owner's time zone: the day starts at their midnight.

    Returns:
        The start of that day in the owner's zone, as a UTC instant, or
        ``None`` to use the usual window.

    Raises:
        ValidationFailedError: If the value is not a ``YYYY-MM-DD`` date.
    """
    if value is None:
        return None
    try:
        day = datetime.strptime(value.strip(), SINCE_FORMAT)
        return day.replace(tzinfo=zone).astimezone(UTC)
    except ValueError as error:
        message = "--since must be a date such as 2026-09-01"
        raise ValidationFailedError(message) from error


def _print(report: CollectionReport) -> None:
    """Print a collection report, one number per line."""
    for line in report.as_lines():
        typer.echo(line)


def _person_line(entry: DirectoryEntry) -> str:
    """Render one person for the people list."""
    channels = "+".join(channel.value for channel in entry.channels) or "-"
    last_contact = entry.last_contact_at.date().isoformat() if entry.last_contact_at else "never"
    return f"{entry.full_name} · {channels} · {entry.message_count} messages · {last_contact}"
