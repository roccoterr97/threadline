"""Read-only calls to Slack's Web API with one workspace's User OAuth Token.

Slack answers almost everything with HTTP 200 and says in the body whether it
worked (``{"ok": false, "error": "invalid_auth"}``). This client turns those
answers into the project's errors:

* a token Slack no longer accepts → :class:`SlackTokenRefusedError`;
* a workspace admin who has not let the app in → :class:`SlackApprovalNeededError`;
* "wait longer than Threadline waits" → :class:`SlackRateLimitedError`;
* anything else → :class:`SourceRequestRejectedError` or
  :class:`SourceUnavailableError`.

Shorter "Retry-After" waits are sat out by the shared retry policy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Final, Self

import httpx
from pydantic import SecretStr

from tracker.domain.slack import SlackConversation, SlackIdentity, SlackMessage, SlackUser
from tracker.infrastructure.slack.parser import (
    conversation_from,
    identity_from,
    message_from,
    slack_ts,
    user_from,
)
from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.slack import (
    SLACK_API_URL,
    SLACK_APPROVAL_ERRORS,
    SLACK_CONVERSATION_TYPES,
    SLACK_LONGEST_WAIT_SECONDS,
    SLACK_MAX_PAGES,
    SLACK_PAGE_SIZE,
    SLACK_RATE_LIMITED_ERROR,
    SLACK_REFUSED_TOKEN_ERRORS,
)
from tracker.shared.errors import (
    SlackApprovalNeededError,
    SlackRateLimitedError,
    SlackTokenRefusedError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)
from tracker.shared.http import get_with_retries
from tracker.shared.logging import get_logger

#: Status Slack answers when a workspace is over its limit.
_TOO_MANY_REQUESTS: Final[int] = 429

#: What every refusal of the token tells the owner to do.
_SET_UP_AGAIN: Final[str] = "run 'uv run tracker setup slack' again"

_log = get_logger(__name__)


class SlackClient:
    """One workspace, read with its owner's User OAuth Token.

    Use it as an async context manager so the connection pool is always closed::

        async with SlackClient(token) as slack:
            me = await slack.who_am_i()
    """

    def __init__(
        self,
        token: SecretStr,
        *,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind the client to one token.

        Args:
            token: The workspace's User OAuth Token (``xoxp-…``).
            sleep: How to wait between attempts; replaced in tests.
        """
        self._token = token
        self._sleep = sleep
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        """Open the connection pool."""
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"Authorization": f"Bearer {self._token.get_secret_value()}"},
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def who_am_i(self) -> SlackIdentity:
        """Ask Slack whose token this is (``auth.test``), which also proves it works.

        Returns:
            The owner's user identifier and the workspace.
        """
        return identity_from(await self._call("auth.test", {}))

    async def direct_conversations(self) -> list[SlackConversation]:
        """List every direct and group direct message the owner is in.

        Returns:
            The conversations, Slack Connect ones included.
        """
        items = await self._pages(
            "users.conversations",
            {"types": SLACK_CONVERSATION_TYPES, "exclude_archived": "true"},
            "channels",
        )
        return [conversation_from(item) for item in items]

    async def history(self, channel_id: str, oldest: datetime) -> list[SlackMessage]:
        """Read a conversation's messages since a moment, thread replies left out.

        Args:
            channel_id: The conversation.
            oldest: The earliest moment wanted.

        Returns:
            The messages, newest first as Slack gives them.
        """
        items = await self._pages(
            "conversations.history",
            {"channel": channel_id, "oldest": slack_ts(oldest), "inclusive": "true"},
            "messages",
        )
        return [message_from(item) for item in items]

    async def replies(
        self, channel_id: str, thread_ts: str, oldest: datetime
    ) -> list[SlackMessage]:
        """Read the replies in one thread since a moment, the thread's first message left out.

        Args:
            channel_id: The conversation.
            thread_ts: The ``ts`` of the message that starts the thread.
            oldest: The earliest moment wanted.

        Returns:
            The replies.
        """
        items = await self._pages(
            "conversations.replies",
            {"channel": channel_id, "ts": thread_ts, "oldest": slack_ts(oldest)},
            "messages",
        )
        return [message for message in map(message_from, items) if message.ts != thread_ts]

    async def members(self, channel_id: str) -> list[str]:
        """List who is in a group direct message.

        Args:
            channel_id: The conversation.

        Returns:
            Their user identifiers, the owner's included.
        """
        items = await self._pages("conversations.members", {"channel": channel_id}, "members")
        return [str(item) for item in items]

    async def user(self, user_id: str) -> SlackUser:
        """Look one account up (``users.info``).

        Args:
            user_id: The account.

        Returns:
            Its name, e-mail address when shared, and whether it is a person.
        """
        payload = await self._call("users.info", {"user": user_id})
        user = payload.get("user")
        return user_from(user if isinstance(user, dict) else {"id": user_id})

    async def _pages(self, method: str, params: dict[str, str], key: str) -> list[Any]:
        """Follow Slack's cursors until the listing ends.

        Args:
            method: The Web API method.
            params: Its parameters, without the cursor.
            key: Where each page keeps its rows.

        Returns:
            Every row of every page.

        Raises:
            SourceUnavailableError: If the listing does not end within
                ``SLACK_MAX_PAGES`` pages.
        """
        rows: list[Any] = []
        cursor = ""
        for _ in range(SLACK_MAX_PAGES):
            page_params = {**params, "limit": str(SLACK_PAGE_SIZE)}
            if cursor:
                page_params["cursor"] = cursor
            payload = await self._call(method, page_params)
            rows.extend(payload.get(key) or [])
            cursor = str((payload.get("response_metadata") or {}).get("next_cursor") or "")
            if not cursor:
                return rows
        message = f"Slack's {method} did not end within {SLACK_MAX_PAGES} pages"
        raise SourceUnavailableError(message)

    async def _call(self, method: str, params: dict[str, str]) -> dict[str, Any]:
        """Call one Web API method and hand back its answer when it worked.

        Args:
            method: The Web API method, such as ``auth.test``.
            params: Its parameters.

        Returns:
            Slack's answer, which said ``ok``.
        """
        response = await self._send(method, params)
        if response.status_code == _TOO_MANY_REQUESTS:
            raise _rate_limited(method, response)
        if response.status_code != httpx.codes.OK:
            _log.error("slack_request_failed", method=method, status=response.status_code)
            message = f"Slack answered status {response.status_code}"
            raise SourceUnavailableError(message)
        payload = _json_of(response, method)
        if payload.get("ok") is not True:
            raise _refusal(method, str(payload.get("error") or "unknown_error"), response)
        return payload

    async def _send(self, method: str, params: dict[str, str]) -> httpx.Response:
        """Send one GET, retrying what is worth retrying."""
        if self._http is None:
            message = "Slack client used outside its context manager"
            raise SourceUnavailableError(message)
        try:
            return await get_with_retries(
                self._http,
                f"{SLACK_API_URL}/{method}",
                params=params,
                source="slack",
                sleep=self._sleep,
                longest_wait=SLACK_LONGEST_WAIT_SECONDS,
            )
        except httpx.HTTPError as error:
            _log.error("slack_unreachable", method=method, error_type=type(error).__name__)
            message = "Slack could not be reached"
            raise SourceUnavailableError(message) from error


def _json_of(response: httpx.Response, method: str) -> dict[str, Any]:
    """Read an answer's JSON body, refusing anything else."""
    try:
        payload: Any = response.json()
    except ValueError as error:
        _log.error("slack_payload_unreadable", method=method)
        message = "Slack answered with something that is not JSON"
        raise SourceUnavailableError(message) from error
    if not isinstance(payload, dict):
        message = "Slack answered with an unexpected payload shape"
        raise SourceUnavailableError(message)
    return payload


def _refusal(
    method: str, error: str, response: httpx.Response
) -> SlackTokenRefusedError | SlackApprovalNeededError | SourceUnavailableError:
    """Turn Slack's ``"ok": false`` into the error the owner can act on.

    Slack's error codes are fixed words such as ``invalid_auth``; they carry
    nothing private, so the code is logged and the one unknown to Threadline is
    named in the message.
    """
    _log.warning("slack_refused", method=method, error=error)
    if error in SLACK_REFUSED_TOKEN_ERRORS:
        message = f"Slack no longer accepts the saved key ({error}) - {_SET_UP_AGAIN}"
        return SlackTokenRefusedError(message)
    if error in SLACK_APPROVAL_ERRORS:
        message = (
            f"Slack says your workspace admin must approve the Threadline app ({error}); "
            f"once they have, {_SET_UP_AGAIN}"
        )
        return SlackApprovalNeededError(message)
    if error == SLACK_RATE_LIMITED_ERROR:
        return _rate_limited(method, response)
    message = f"Slack refused {method}: {error}"
    return SourceRequestRejectedError(message)


def _rate_limited(method: str, response: httpx.Response) -> SlackRateLimitedError:
    """The error for Slack asking Threadline to wait longer than it waits."""
    wait = response.headers.get("Retry-After", "?")
    _log.warning("slack_rate_limited", method=method, retry_after=wait)
    message = (
        f"Slack asked Threadline to wait {wait} seconds before reading more; "
        "the next run reads the rest"
    )
    return SlackRateLimitedError(message)


async def check_slack_token(token: SecretStr) -> SlackIdentity:
    """Make one small Slack call with a token, to prove it works.

    Args:
        token: The token to try.

    Returns:
        Who it belongs to.
    """
    async with SlackClient(token) as slack:
        return await slack.who_am_i()
