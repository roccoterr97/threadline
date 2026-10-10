"""The set-up's view of LinkedIn: sign in with the owner's own application, and keep its secret.

It puts together the consent page, the one-time listener on this computer, the
key exchange and the encrypted store, so the set-up step can make and renew
the LinkedIn key without knowing how any of them works.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime

from pydantic import SecretStr
from supabase import Client

from tracker.domain.linkedin_sign_in import LinkedInApp, LinkedInGrant, SignInProblem
from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.linkedin.callback import CallbackAnswer, CallbackListener
from tracker.infrastructure.linkedin.oauth import LinkedInOAuthApi, authorization_url
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.clock import Clock
from tracker.shared.constants.linkedin_sign_in import (
    CANCELLED_ERRORS,
    CLIENT_SECRET_NAME,
    ERROR_DESCRIPTION_MAX_CHARACTERS,
    REDIRECT_URL,
    SCOPE_ERRORS,
    STATE_BYTES,
    WAIT_SLICE_SECONDS,
)
from tracker.shared.constants.setup import LINKEDIN_PRODUCT
from tracker.shared.errors import LinkedInSignInError
from tracker.shared.logging import get_logger

#: Opens a listener for one sign-in's state; replaced in tests.
ListenerFactory = Callable[[str], CallbackListener]

_log = get_logger(__name__)


class LinkedInConnection:
    """Makes a LinkedIn key with the owner's application, and keeps the application's secret."""

    def __init__(
        self,
        connect: Callable[[str, SecretStr], Client],
        clock: Clock,
        *,
        api: LinkedInOAuthApi | None = None,
        listener_for: ListenerFactory = CallbackListener,
        wait_slice_seconds: float = WAIT_SLICE_SECONDS,
        redirect_url: str = REDIRECT_URL,
    ) -> None:
        """Bind the connection to a database client factory and a clock.

        Args:
            connect: Builds a Supabase client from an address and a secret key.
            clock: Stamps the stored secret and dates the key.
            api: LinkedIn's sign-in endpoints; built on ``clock`` when omitted.
            listener_for: Opens the one-time listener; replaced in tests.
            wait_slice_seconds: How long to wait before asking whether to keep waiting.
            redirect_url: Where LinkedIn sends its answer; replaced in tests.
        """
        self._connect = connect
        self._clock = clock
        self._api = api or LinkedInOAuthApi(clock)
        self._listener_for = listener_for
        self._wait_slice_seconds = wait_slice_seconds
        self._redirect_url = redirect_url

    async def sign_in(
        self,
        app: LinkedInApp,
        show_page: Callable[[str], None],
        keep_waiting: Callable[[], bool],
    ) -> LinkedInGrant:
        """Open LinkedIn's consent page, wait for the answer and trade it for a key.

        Args:
            app: The owner's application.
            show_page: Opens the consent page, or offers it as a link.
            keep_waiting: Asked each time no answer came in a while; ``False`` stops.

        Returns:
            The new key.

        Raises:
            LinkedInSignInError: If the owner cancelled, LinkedIn refused, the
                port is busy, or no answer came.
            SourceUnavailableError: If LinkedIn could not be reached.
        """
        state = secrets.token_urlsafe(STATE_BYTES)
        with self._listener_for(state) as listener:
            show_page(authorization_url(app.client_id, state, self._redirect_url))
            answer = await listener.wait(self._wait_slice_seconds)
            while answer is None and keep_waiting():
                answer = await listener.wait(self._wait_slice_seconds)
            if answer is None:
                # LinkedIn may have answered while the question was on screen.
                answer = await listener.wait(0)
        if answer is None:
            raise _no_answer()
        code = _code_from(answer)
        grant = await self._api.exchange(app, code, self._redirect_url)
        _log.info("linkedin_key_made", expiry_known=grant.expires_at is not None)
        return grant

    async def expiry_of(self, app: LinkedInApp, token: SecretStr) -> datetime | None:
        """Ask LinkedIn when a key made for the application stops working.

        Args:
            app: The owner's application.
            token: The key.

        Returns:
            When it stops working, or ``None`` when LinkedIn did not say.
        """
        return await self._api.expiry_of(app, token)

    async def saved_client_secret(self, access: StoreAccess) -> SecretStr | None:
        """Read the application's Client Secret from the encrypted store.

        Args:
            access: What reaching the store needs.

        Returns:
            The secret, or ``None`` when none was saved.
        """
        value = self._store(access).get_secret(CLIENT_SECRET_NAME)
        return SecretStr(value) if value else None

    async def save_client_secret(self, access: StoreAccess, secret: SecretStr) -> None:
        """Keep the application's Client Secret, encrypted, replacing any earlier one.

        Args:
            access: What reaching the store needs.
            secret: The Client Secret LinkedIn just accepted.
        """
        self._store(access).put_secret(CLIENT_SECRET_NAME, secret.get_secret_value())

    def _store(self, access: StoreAccess) -> SecretStore:
        """Build the encrypted store on the saved project."""
        repository = AppSecretRepository(self._connect(access.supabase_url, access.service_key))
        return SecretStore(repository, access.encryption_key, self._clock)


def _code_from(answer: CallbackAnswer) -> str:
    """Take the one-time code out of LinkedIn's answer, or say why there is none.

    Args:
        answer: What LinkedIn sent back.

    Returns:
        The code.

    Raises:
        LinkedInSignInError: If LinkedIn sent an error instead.
    """
    if answer.code and not answer.error:
        return answer.code
    error = answer.error or ""
    _log.warning("linkedin_consent_refused", error=error)
    if error in CANCELLED_ERRORS:
        message = "LinkedIn says the sign-in was cancelled, so no key was made"
        raise LinkedInSignInError(message, SignInProblem.CANCELLED)
    if error in SCOPE_ERRORS:
        message = (
            f"LinkedIn has not given your application the '{LINKEDIN_PRODUCT}' product. "
            "LinkedIn offers it only to profiles located in the EEA or Switzerland; if "
            "yours is, check that the application's Products tab lists it"
        )
        raise LinkedInSignInError(message, SignInProblem.PRODUCT_MISSING)
    said = " ".join((answer.error_description or error or "no reason given").split())
    message = f"LinkedIn did not make a key. It said: {said[:ERROR_DESCRIPTION_MAX_CHARACTERS]}"
    raise LinkedInSignInError(message, SignInProblem.OTHER)


def _no_answer() -> LinkedInSignInError:
    """The error for a sign-in LinkedIn never answered."""
    message = (
        "No answer came back from LinkedIn. If LinkedIn's page showed an error such as "
        "'redirect_uri does not match' or 'invalid client_id', the address on the Auth "
        "tab or the Client ID is not exactly right"
    )
    return LinkedInSignInError(message, SignInProblem.NO_ANSWER)
