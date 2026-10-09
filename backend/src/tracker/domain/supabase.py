"""What a Supabase account holds, as the set-up sees it: organizations, projects, keys.

Plain values shared by the set-up steps and the Management API client; no
HTTP, no framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr

from tracker.shared.constants.setup import RegionGroup


@dataclass(frozen=True, slots=True)
class Organization:
    """One Supabase organization the token's owner belongs to.

    Attributes:
        slug: The identifier the Management API uses.
        name: The name shown in the dashboard.
    """

    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class SupabaseProject:
    """One Supabase project, as the Management API describes it.

    Attributes:
        ref: The project's identifier, the first part of its address.
        name: The name shown in the dashboard.
        organization_slug: The organization that owns it.
        status: Supabase's status word, such as ``ACTIVE_HEALTHY`` or ``COMING_UP``.
    """

    ref: str
    name: str
    organization_slug: str
    status: str


@dataclass(frozen=True, slots=True)
class NewProject:
    """What a new project is created with.

    Attributes:
        organization_slug: The organization to create it in.
        name: Its name.
        region: Supabase's smart region group; it picks the data centre.
        database_password: The database's password; generated and never kept.
    """

    organization_slug: str
    name: str
    region: RegionGroup
    database_password: SecretStr


class ApiKeyKind(StrEnum):
    """The two kinds of API key a project has; legacy JWT keys are left alone."""

    PUBLISHABLE = "publishable"
    SECRET = "secret"


@dataclass(frozen=True, slots=True)
class ApiKey:
    """One of a project's API keys.

    Attributes:
        kind: Publishable or secret.
        name: The name shown in the dashboard.
        value: The key itself, when Supabase revealed it.
    """

    kind: ApiKeyKind
    name: str
    value: SecretStr | None


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """The auth settings the set-up changes; a field left ``None`` is not sent.

    Attributes:
        disable_signup: Whether strangers are prevented from creating a login.
        site_url: Where a login link lands by default.
        redirect_urls: Every address a login link may land on.
    """

    disable_signup: bool | None = None
    site_url: str | None = None
    redirect_urls: tuple[str, ...] | None = None
