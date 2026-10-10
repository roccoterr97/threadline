"""What a Supabase account holds, as the set-up sees it: organizations, projects, keys.

Plain values shared by the set-up steps and the Management API client; no
HTTP, no framework.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

from pydantic import SecretStr

from tracker.shared.constants.setup import SUPABASE_HOST_SUFFIX, RegionGroup

#: What a project's identifier is made of: the first part of its address.
PROJECT_REF_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]{8,40}$")

_HTTPS: Final[str] = "https"


def project_ref_of(url: str) -> str | None:
    """Read the project identifier out of a project address.

    Args:
        url: ``https://<project-ref>.supabase.co``.

    Returns:
        The identifier, or ``None`` when the address is not a Supabase project address.
    """
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    ref = host.removesuffix(SUPABASE_HOST_SUFFIX)
    if parts.scheme != _HTTPS or ref == host or not PROJECT_REF_PATTERN.match(ref):
        return None
    return ref


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


@dataclass(frozen=True, slots=True)
class SealedAccessToken:
    """The access token a browser sign-in made, as Supabase hands it over: sealed.

    Only the computer holding the private key whose public half went into the
    sign-in page can open it, so the token never travels in the clear.

    Attributes:
        ciphertext_hex: The sealed token with its 16-byte check appended, in hex.
        public_key_hex: Supabase's one-off public key for this sign-in, in hex.
        nonce_hex: The seal's nonce, in hex.
    """

    ciphertext_hex: str
    public_key_hex: str
    nonce_hex: str
