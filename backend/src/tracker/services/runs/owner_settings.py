"""Copy the owner's settings the database needs into the database.

The dashboard's "overdue" and "time to chase" are decided by the
``people_overview`` view, which measures due dates against
``public.owner_today()``. That function reads the owner's time zone from the
one row of ``app_settings``. The zone itself is configured once, in
``OWNER_TIME_ZONE``, and this module is the only thing that writes it into the
database — at the start of every daily run, so a changed setting reaches the
dashboard the next morning at the latest.
"""

from __future__ import annotations

from tracker.repositories import Repositories
from tracker.shared.config import Settings
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def publish_owner_settings(repositories: Repositories, settings: Settings) -> str:
    """Write the configured time zone into ``app_settings``.

    Safe to repeat: the row is keyed on its singleton column, so writing the
    same zone twice changes nothing.

    Args:
        repositories: The repository container.
        settings: The process configuration holding the owner's time zone.

    Returns:
        The zone written, as configured.

    Raises:
        DatabaseUnavailableError: If the database could not be reached or
            refused the zone.
    """
    zone = settings.owner_time_zone
    repositories.app_settings.save_time_zone(zone)
    _log.info("owner_settings_published", time_zone=zone)
    return zone
