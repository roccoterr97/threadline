"""The set-up's view of the Microsoft sign-ins: is there one, and make one.

It puts together the pieces Threadline already has — the encrypted store, the
one-time-code sign-in, the calendar read and the Teams profile read — so the
set-up can sign in and say who signed in, without knowing how any of them work.
There are two sign-ins, each with its own key: Outlook, and Teams chats.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pydantic import SecretStr
from supabase import Client

from tracker.infrastructure.microsoft.auth import (
    OUTLOOK_SIGN_IN,
    TEAMS_SIGN_IN,
    MicrosoftAuthenticator,
    MicrosoftSignIn,
)
from tracker.infrastructure.microsoft.probe import GraphProbe
from tracker.infrastructure.microsoft.teams import TeamsChats
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.clock import Clock

#: Shows the one-time code: (page address, code).
ShowCode = Callable[[str, str], None]


@dataclass(frozen=True, slots=True)
class MicrosoftAccess:
    """What signing in to Microsoft needs.

    Attributes:
        supabase_url: The project address, where the key is stored.
        service_key: The secret key of that project.
        encryption_key: Locks the stored key.
        client_id: The registered application to sign in through.
        tenant: Which Microsoft accounts may sign in.
    """

    supabase_url: str
    service_key: SecretStr
    encryption_key: SecretStr
    client_id: str
    tenant: str


class MicrosoftConnection:
    """Signs in to Microsoft and stores the key, for the set-up."""

    def __init__(self, connect: Callable[[str, SecretStr], Client], clock: Clock) -> None:
        """Bind the connection to a database client factory and a clock.

        Args:
            connect: Builds a Supabase client from an address and a secret key.
            clock: Supplies the rotation time of the stored key.
        """
        self._connect = connect
        self._clock = clock

    async def is_signed_in(self, access: MicrosoftAccess) -> bool:
        """Tell whether an Outlook sign-in key is stored.

        Args:
            access: What the sign-in needs.

        Returns:
            ``True`` when a key is stored.
        """
        return self._has_key(access, OUTLOOK_SIGN_IN)

    async def sign_in(self, access: MicrosoftAccess, show_code: ShowCode) -> str:
        """Run the Outlook one-time-code sign-in, then read who signed in.

        Args:
            access: What the sign-in needs.
            show_code: Shows the page and the code to type there.

        Returns:
            The signed-in address; empty when Microsoft does not say.
        """
        async with (
            self._signed_in(access, show_code, OUTLOOK_SIGN_IN) as authenticator,
            GraphProbe(authenticator) as graph,
        ):
            return await graph.calendar_owner()

    async def is_signed_in_to_teams(self, access: MicrosoftAccess) -> bool:
        """Tell whether a Teams sign-in key is stored.

        Args:
            access: What the sign-in needs.

        Returns:
            ``True`` when a key is stored.
        """
        return self._has_key(access, TEAMS_SIGN_IN)

    async def sign_in_to_teams(self, access: MicrosoftAccess, show_code: ShowCode) -> str:
        """Run the Teams one-time-code sign-in, then read who signed in.

        Args:
            access: What the sign-in needs; its tenant must take work accounts.
            show_code: Shows the page and the code to type there.

        Returns:
            The signed-in address; empty when Microsoft does not say.
        """
        async with (
            self._signed_in(access, show_code, TEAMS_SIGN_IN) as authenticator,
            TeamsChats(authenticator) as teams,
        ):
            return (await teams.signed_in_user()).email

    @asynccontextmanager
    async def _signed_in(
        self, access: MicrosoftAccess, show_code: ShowCode, sign_in: MicrosoftSignIn
    ) -> AsyncIterator[MicrosoftAuthenticator]:
        """Show the code, wait for the sign-in, and lend the signed-in authenticator."""
        store = SecretStore(self._repository(access), access.encryption_key, self._clock)
        authenticator = MicrosoftAuthenticator(
            store, self._clock, client_id=access.client_id, tenant=access.tenant, sign_in=sign_in
        )
        async with authenticator:
            prompt = await authenticator.request_device_code()
            show_code(prompt.verification_url, prompt.user_code)
            await authenticator.wait_for_sign_in(prompt)
            yield authenticator

    def _has_key(self, access: MicrosoftAccess, sign_in: MicrosoftSignIn) -> bool:
        """Tell whether one sign-in's key is stored."""
        return self._repository(access).find_by_name(sign_in.secret_name) is not None

    def _repository(self, access: MicrosoftAccess) -> AppSecretRepository:
        """Build the secrets table's repository for the saved project."""
        client = self._connect(access.supabase_url, access.service_key)
        return AppSecretRepository(client)
