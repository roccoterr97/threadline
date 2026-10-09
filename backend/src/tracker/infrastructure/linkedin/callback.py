"""A one-time listener on this computer for LinkedIn's answer to the sign-in.

After the owner clicks "Allow", LinkedIn sends the browser to the redirect
address registered on the application's Auth tab, with a one-time code. This
listens on that address, on this computer only, until an answer carrying the
expected ``state`` arrives. An answer with any other state is turned away, so
another web page cannot slip in a code of its own; the first matching answer
is kept and every later one ignored.
"""

from __future__ import annotations

import asyncio
import hmac
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Final, Self, cast
from urllib.parse import parse_qs, urlsplit

from tracker.domain.linkedin_sign_in import SignInProblem
from tracker.shared.constants.linkedin_sign_in import (
    CALLBACK_ADDRESSES,
    CALLBACK_PATH,
    CALLBACK_PORT,
    POLL_SECONDS,
    STOP_POLL_SECONDS,
)
from tracker.shared.errors import LinkedInSignInError
from tracker.shared.logging import get_logger

#: What the browser tab shows once LinkedIn's answer is in.
_RECEIVED_PAGE: Final[str] = (
    "Threadline has LinkedIn's answer. You can close this tab and go back to the set-up."
)

#: What it shows for an answer that belongs to another, older sign-in.
_STALE_PAGE: Final[str] = (
    "This answer is not for the Threadline set-up that is running now. "
    "Go back to the set-up and try again from there."
)

#: The page may load nothing at all.
_CONTENT_SECURITY_POLICY: Final[str] = "default-src 'none'; frame-ancestors 'none'"

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CallbackAnswer:
    """What LinkedIn sent back to this computer.

    Attributes:
        code: The one-time code, when the owner allowed it.
        error: LinkedIn's error word, when it did not hand out a code.
        error_description: LinkedIn's own explanation of that error.
    """

    code: str | None
    error: str | None
    error_description: str | None


class _Handler(BaseHTTPRequestHandler):
    """Answers the browser's one request; one instance per request."""

    @property
    def listener(self) -> CallbackListener:
        """The listener this request reached."""
        return cast(_CallbackServer, self.server).listener

    def do_GET(self) -> None:  # noqa: N802 - the name the standard library calls
        """Take LinkedIn's answer when its state matches, otherwise turn it away."""
        parts = urlsplit(self.path)
        if parts.path != CALLBACK_PATH:
            self._reply(HTTPStatus.NOT_FOUND, "Nothing here.")
            return
        query = parse_qs(parts.query)
        if not self.listener.expects(_first(query, "state")):
            _log.warning("linkedin_callback_state_mismatch")
            self._reply(HTTPStatus.BAD_REQUEST, _STALE_PAGE)
            return
        self.listener.receive(
            CallbackAnswer(
                code=_first(query, "code"),
                error=_first(query, "error"),
                error_description=_first(query, "error_description"),
            )
        )
        self._reply(HTTPStatus.OK, _RECEIVED_PAGE)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - inherited name
        """Keep the request log, which holds the one-time code, out of the terminal."""

    def _reply(self, status: HTTPStatus, text: str) -> None:
        body = f"<!doctype html><meta charset='utf-8'><title>Threadline</title><p>{text}</p>"
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(encoded)


class _CallbackServer(ThreadingHTTPServer):
    """One listening address, carrying the listener its handlers report to."""

    daemon_threads = True

    # On Windows, SO_REUSEADDR lets a second program bind a port that is already
    # listening, so a busy port would go unnoticed and LinkedIn's answer could reach
    # the other program. Elsewhere it only allows quick re-use after a close.
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, address: str, port: int, listener: CallbackListener) -> None:
        """Listen on one address.

        Args:
            address: ``127.0.0.1`` or ``::1``.
            port: The port; ``0`` lets the system pick one (tests only).
            listener: Where answers are reported.
        """
        if ":" in address:
            self.address_family = socket.AF_INET6
        super().__init__((address, port), _Handler)
        self.listener = listener

    def server_bind(self) -> None:
        """Bind, on Windows claiming the port so no other program can share it."""
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CallbackListener:
    """Listens for LinkedIn's answer while the owner signs in.

    Use it as a context manager, so the port is always given back::

        with CallbackListener(state) as listener:
            answer = await listener.wait(120)
    """

    def __init__(
        self,
        state: str,
        *,
        port: int = CALLBACK_PORT,
        addresses: tuple[str, ...] = CALLBACK_ADDRESSES,
    ) -> None:
        """Prepare to listen for one sign-in.

        Args:
            state: The random value sent to LinkedIn, which comes back with its answer.
            port: The port in the registered address.
            addresses: Where to listen; the first one must work, the others may not.
        """
        self._state = state
        self._port = port
        self._addresses = addresses
        self._servers: list[_CallbackServer] = []
        self._lock = threading.Lock()
        self._arrived = threading.Event()
        self._answer: CallbackAnswer | None = None

    def __enter__(self) -> Self:
        """Start listening.

        Raises:
            LinkedInSignInError: If another program already uses the port.
        """
        first, *others = self._addresses
        try:
            self._servers.append(_CallbackServer(first, self._port, self))
        except OSError as error:
            _log.error("linkedin_callback_port_busy", port=self._port, errno=error.errno)
            message = (
                f"Another program on this computer is using port {self._port}, where "
                "LinkedIn sends its answer. Close that program, or make the key by hand"
            )
            raise LinkedInSignInError(message, SignInProblem.OTHER) from error
        for address in others:
            try:
                self._servers.append(_CallbackServer(address, self.port, self))
            except OSError:
                _log.info("linkedin_callback_address_skipped", address=address)
        for server in self._servers:
            threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": STOP_POLL_SECONDS},
                name="linkedin-callback",
                daemon=True,
            ).start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop listening and give the port back."""
        for server in self._servers:
            server.shutdown()
            server.server_close()
        self._servers.clear()

    @property
    def port(self) -> int:
        """The port actually listened on; differs from the one asked for only with ``0``."""
        if not self._servers:
            return self._port
        return int(self._servers[0].server_address[1])

    def expects(self, state: str | None) -> bool:
        """Tell whether an answer carries this sign-in's state.

        Args:
            state: The state the answer carries, if any.

        Returns:
            ``True`` only for exactly the state sent to LinkedIn.
        """
        if state is None:
            return False
        return hmac.compare_digest(state.encode(), self._state.encode())

    def receive(self, answer: CallbackAnswer) -> None:
        """Keep the first matching answer; later ones change nothing.

        Args:
            answer: What LinkedIn sent.
        """
        with self._lock:
            if self._answer is None:
                self._answer = answer
                self._arrived.set()

    async def wait(self, seconds: float) -> CallbackAnswer | None:
        """Wait for the answer, without holding up anything else.

        Args:
            seconds: How long to wait at most.

        Returns:
            The answer, or ``None`` when none arrived in time.
        """
        deadline = time.monotonic() + seconds
        while not self._arrived.is_set():
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(POLL_SECONDS)
        return self._answer


def _first(query: dict[str, list[str]], name: str) -> str | None:
    """Read one query value, or ``None`` when it is absent."""
    values = query.get(name)
    return values[0] if values else None
