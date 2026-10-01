"""The set-up's view of the Microsoft sign-in: is there one, and make one.

It puts together the pieces Threadline already has — the encrypted store, the
one-time-code sign-in and the calendar read — so the set-up can sign in and say
who signed in, without knowing how any of them work.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import SecretStr
from supabase import Client

from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.probe import GraphProbe
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
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
        """Tell whether a sign-in key is stored.

        Args:
            access: What the sign-in needs.

        Returns:
            ``True`` when a key is stored.
        """
        return self._repository(access).find_by_name(MICROSOFT_REFRESH_TOKEN) is not None

    async def sign_in(self, access: MicrosoftAccess, show_code: ShowCode) -> str:
        """Run the one-time-code sign-in, then read who signed in.

        Args:
            access: What the sign-in needs.
            show_code: Shows the page and the code to type there.

        Returns:
            The signed-in address; empty when Microsoft does not say.
        """
        store = SecretStore(self._repository(access), access.encryption_key, self._clock)
        authenticator = MicrosoftAuthenticator(
            store, self._clock, client_id=access.client_id, tenant=access.tenant
        )
        async with authenticator:
            prompt = await authenticator.request_device_code()
            show_code(prompt.verification_url, prompt.user_code)
            await authenticator.wait_for_sign_in(prompt)
            async with GraphProbe(authenticator) as graph:
                return await graph.calendar_owner()

    def _repository(self, access: MicrosoftAccess) -> AppSecretRepository:
        """Build the secrets table's repository for the saved project."""
        client = self._connect(access.supabase_url, access.service_key)
        return AppSecretRepository(client)
