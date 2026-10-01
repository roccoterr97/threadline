"""System commands: the health check and the sample data.

``tracker healthcheck`` is the one command that proves the whole chain works:
configuration loads, the database answers, and a secret can be written, read
back and removed again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

import typer
from supabase import Client

from tracker.infrastructure.database import create_database_client, probe_database
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import build_repositories
from tracker.services.sample_data import (
    SAMPLE_DATA_FILE,
    SampleDataService,
    TableCount,
    read_sample_data,
)
from tracker.shared.clock import SystemClock
from tracker.shared.config import Settings, get_settings
from tracker.shared.constants.retry import HEALTHCHECK_ATTEMPTS, HEALTHCHECK_DELAY_SECONDS
from tracker.shared.constants.setup import SECRET_PROBE_NAME, SECRET_PROBE_VALUE
from tracker.shared.errors import ValidationFailedError

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "system"

sample_app = typer.Typer(
    help="Load or clear the made-up sample data.",
    no_args_is_help=True,
)

FileOption = Annotated[
    Path,
    typer.Option("--file", help="Sample data file to use.", show_default=False),
]


def register(cli: typer.Typer) -> None:
    """Attach the system commands to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.command("healthcheck", rich_help_panel=HELP_PANEL)(healthcheck)
    cli.add_typer(sample_app, name="sample", rich_help_panel=HELP_PANEL)


def healthcheck() -> None:
    """Check the configuration, the database and the secret store."""
    settings = get_settings()
    client = create_database_client(settings)
    probe_database(
        client,
        attempts=HEALTHCHECK_ATTEMPTS,
        delay_seconds=HEALTHCHECK_DELAY_SECONDS,
    )
    _check_secret_store(settings, client)
    typer.echo("configuration ok · database reachable · secret store ok")


@sample_app.command("load")
def load_sample(file: FileOption = SAMPLE_DATA_FILE) -> None:
    """Write the made-up sample records. Running it twice changes nothing."""
    dataset = read_sample_data(file)
    service = _sample_service()
    _report("loaded", service.load(dataset))


@sample_app.command("clear")
def clear_sample(file: FileOption = SAMPLE_DATA_FILE) -> None:
    """Remove the made-up sample records, leaving real data untouched."""
    dataset = read_sample_data(file)
    service = _sample_service()
    _report("cleared", service.clear(dataset))


def _sample_service() -> SampleDataService:
    """Build the sample-data service on a fresh database client."""
    client = create_database_client(get_settings())
    return SampleDataService(build_repositories(client))


def _check_secret_store(settings: Settings, client: Client) -> None:
    """Write, read back and remove a throw-away secret.

    Args:
        settings: The process configuration.
        client: The Supabase client to use.

    Raises:
        ValidationFailedError: If the value does not survive the round trip.
    """
    store = SecretStore(
        build_repositories(client).app_secrets,
        settings.token_encryption_key,
        SystemClock(),
    )
    if not store.round_trips(SECRET_PROBE_NAME, SECRET_PROBE_VALUE):
        message = "secret store did not return the value it was given"
        raise ValidationFailedError(message)


def _report(action: str, counts: tuple[TableCount, ...]) -> None:
    """Print one line per table plus a total.

    Args:
        action: Past-tense verb shown in the total line.
        counts: What each table gained or lost.
    """
    for count in counts:
        typer.echo(f"{count.table}: {count.rows}")
    typer.echo(f"{action} {sum(count.rows for count in counts)} rows")
