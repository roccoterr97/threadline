"""Where the owner opens the dashboard, and the personal link to the shared one.

The shared dashboard (``HOSTED_DASHBOARD_URL``) is one page for every owner, so
by itself it does not know whose database to open. A personal link tells it,
after the ``#``: ``https://app.threadlineapp.com/#project=<ref>&key=<key>``.
Browsers never send what follows the ``#`` to the web host, so neither value
reaches its logs; both are public by design anyway, the same two values a
dashboard's own ``config.js`` carries. Every page of the dashboard takes the
same ending, so a link from the morning e-mail to ``/review`` also works on a
phone that has never opened the dashboard before.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import quote, urlencode

from tracker.domain.supabase import project_ref_of
from tracker.shared.constants.dashboard import (
    CONNECT_KEY_PARAMETER,
    CONNECT_PROJECT_PARAMETER,
    HOSTED_DASHBOARD_URL,
    PRIVILEGED_KEY_ROLES,
    SUPABASE_SECRET_KEY_PREFIX,
)
from tracker.shared.errors import ValidationFailedError

#: What a publishable key (``sb_publishable_...``) or a legacy public key (a JWT) is made of.
_PUBLIC_KEY: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]+$")
#: A legacy key is a JWT: header, claims and signature, joined by dots.
_JWT_PARTS: Final[int] = 3
#: The start page's path, written out before a ``#`` so the link reads plainly.
_START_PAGE: Final[str] = "/"


@dataclass(frozen=True, slots=True)
class DashboardAddress:
    """The dashboard's address, and what makes a link to it personal.

    Attributes:
        base: Its address with no trailing slash, as ``DASHBOARD_BASE_URL`` holds it.
        connect: What follows the ``#`` of a personal link; ``None`` for a
            dashboard that knows its database already (an owner's own copy),
            or for the shared one when the link could not be made.
    """

    base: str
    connect: str | None = None

    @property
    def shared(self) -> bool:
        """Whether this is Threadline's shared dashboard rather than the owner's own copy."""
        return self.base == HOSTED_DASHBOARD_URL

    def page(self, path: str = "") -> str:
        """The address of one page, personal when the dashboard is the shared one.

        Args:
            path: The page, such as ``/review``; empty for the start page.

        Returns:
            The address to open.
        """
        if self.connect is None:
            return f"{self.base}{path}"
        return f"{self.base}{path or _START_PAGE}#{self.connect}"


def require_public_key(key: str) -> str:
    """Refuse a key the browser must never hold.

    Args:
        key: What ``SUPABASE_ANON_KEY`` holds.

    Returns:
        The key, unchanged.

    Raises:
        ValidationFailedError: If it is not plain text or is a secret key.
    """
    if not _PUBLIC_KEY.match(key):
        message = "SUPABASE_ANON_KEY should hold only letters, digits, '.', '_' and '-'"
        raise ValidationFailedError(message)
    if key.startswith(SUPABASE_SECRET_KEY_PREFIX) or _legacy_role(key) in PRIVILEGED_KEY_ROLES:
        message = "SUPABASE_ANON_KEY holds a secret key - put the publishable key there"
        raise ValidationFailedError(message)
    return key


def connect_fragment(project_url: str, publishable_key: str) -> str:
    """What follows the ``#`` of a personal link: the project and its publishable key.

    Args:
        project_url: ``https://<project-ref>.supabase.co``.
        publishable_key: The publishable ("anon") key, never the secret one.

    Returns:
        ``project=<ref>&key=<key>``.

    Raises:
        ValidationFailedError: If the address is not a project address, or the
            key is not one the browser may hold.
    """
    ref = project_ref_of(project_url)
    if ref is None:
        message = "SUPABASE_URL should look like https://<project-id>.supabase.co"
        raise ValidationFailedError(message)
    key = require_public_key(publishable_key.strip())
    pairs = {CONNECT_PROJECT_PARAMETER: ref, CONNECT_KEY_PARAMETER: key}
    return urlencode(pairs, quote_via=quote)


def dashboard_address(
    base_url: str | None, project_url: str, publishable_key: str
) -> DashboardAddress | None:
    """The dashboard the owner opens, with the personal part when it is the shared one.

    Never raises: a shared dashboard whose personal part cannot be made (a key
    that is not the publishable one) gets none, since its plain address still
    opens it on a device that was connected before. Callers that can say so
    check :attr:`DashboardAddress.shared` against a missing ``connect``.

    Args:
        base_url: What ``DASHBOARD_BASE_URL`` holds, or ``None`` when it is unset.
        project_url: ``https://<project-ref>.supabase.co``.
        publishable_key: The publishable ("anon") key.

    Returns:
        The address, or ``None`` when the dashboard has none yet.
    """
    if not base_url or not base_url.strip():
        return None
    base = base_url.strip().rstrip("/")
    if base != HOSTED_DASHBOARD_URL:
        return DashboardAddress(base)
    try:
        return DashboardAddress(base, connect_fragment(project_url, publishable_key))
    except ValidationFailedError:
        return DashboardAddress(base)


def _legacy_role(key: str) -> str | None:
    """The ``role`` a legacy (JWT) key claims, or ``None`` when it is not one or unreadable.

    Only the claims are read, to tell the public key from the service-role key;
    the signature is Supabase's to check, so it is not.
    """
    parts = key.split(".")
    if len(parts) != _JWT_PARTS:
        return None
    claims = parts[1]
    try:
        decoded = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    except (binascii.Error, ValueError):
        return None
    role = decoded.get("role") if isinstance(decoded, dict) else None
    return role if isinstance(role, str) else None
