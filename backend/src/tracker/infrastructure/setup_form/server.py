"""A small web server on this computer that shows the set-up page and takes its answers.

It listens on the loopback address only, on a port the system picks, and
every request that reads or answers the conversation must carry a key that
only the opened page and whoever reads the command's output know: it travels
in the address's fragment, which the browser never sends anywhere, and the
address is printed where the command was started so it can be opened by hand.
The Host header is checked too, so a web page from elsewhere cannot reach it by
a renamed address.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final, cast
from urllib.parse import parse_qs, urlsplit

from tracker.infrastructure.setup_form.conversation import Conversation, Outcome
from tracker.infrastructure.setup_form.io import FormIO
from tracker.shared.constants.setup import (
    FORM_FAREWELL_SECONDS,
    FORM_HOST,
    FORM_KEY_BYTES,
    FORM_KEY_HEADER,
    FORM_MAX_BODY_BYTES,
    FORM_WAIT_SLICE_SECONDS,
)

#: The page's files, served as they are.
ASSETS_DIRECTORY: Final[Path] = Path(__file__).parent / "assets"

#: Which file answers which path, and what it is.
_ASSETS: Final[Mapping[str, tuple[str, str]]] = {
    "/": ("page.html", "text/html; charset=utf-8"),
    "/page.css": ("page.css", "text/css; charset=utf-8"),
    "/page.js": ("page.js", "text/javascript; charset=utf-8"),
}

#: The page may load only its own files and talk only to this server.
_CONTENT_SECURITY_POLICY: Final[str] = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

#: Headers every answer carries.
_COMMON_HEADERS: Final[Mapping[str, str]] = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

_STATE_PATH: Final[str] = "/api/state"
_ANSWER_PATH: Final[str] = "/api/answer"
_STOP_PATH: Final[str] = "/api/stop"


class _Handler(BaseHTTPRequestHandler):
    """Answers the page's requests; one instance per request."""

    @property
    def form(self) -> _FormHttpServer:
        """The server this request came through, with the conversation and the key."""
        return cast(_FormHttpServer, self.server)

    def do_GET(self) -> None:  # noqa: N802 - the name the standard library calls
        """Serve the page's files, or the state."""
        if not self._host_allowed():
            self._deny()
            return
        parts = urlsplit(self.path)
        asset = _ASSETS.get(parts.path)
        if asset is not None:
            self._send_asset(*asset)
            return
        if parts.path != _STATE_PATH:
            self._send(HTTPStatus.NOT_FOUND, b"", "text/plain; charset=utf-8")
            return
        if not self._key_matches():
            self._deny()
            return
        after = _first_int(parse_qs(parts.query).get("after"))
        self._send_json(self.form.conversation.snapshot(after))

    def do_POST(self) -> None:  # noqa: N802 - the name the standard library calls
        """Take an answer, or the wish to stop."""
        if not self._host_allowed() or not self._key_matches():
            self._deny()
            return
        path = urlsplit(self.path).path
        if path == _STOP_PATH:
            self.form.conversation.stop()
            self._send_json({"ok": True})
            return
        if path != _ANSWER_PATH:
            self._send(HTTPStatus.NOT_FOUND, b"", "text/plain; charset=utf-8")
            return
        body = self._read_json()
        if body is None:
            self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain; charset=utf-8")
            return
        accepted = self.form.conversation.answer(
            _as_int(body.get("id")), str(body.get("value", ""))
        )
        self._send_json({"ok": accepted})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - inherited name
        """Keep the request log out of the terminal, where the set-up's own lines are."""

    # --- Checks ---------------------------------------------------------------

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        return host in self.form.allowed_hosts

    def _key_matches(self) -> bool:
        sent = self.headers.get(FORM_KEY_HEADER, "")
        return hmac.compare_digest(sent.encode(), self.form.key.encode())

    def _read_json(self) -> dict[str, object] | None:
        length = _as_int(self.headers.get("Content-Length"))
        if length <= 0 or length > FORM_MAX_BODY_BYTES:
            return None
        try:
            parsed = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    # --- Answers --------------------------------------------------------------

    def _send_asset(self, name: str, content_type: str) -> None:
        self._send(HTTPStatus.OK, (ASSETS_DIRECTORY / name).read_bytes(), content_type)

    def _send_json(self, payload: Mapping[str, object]) -> None:
        self._send(HTTPStatus.OK, json.dumps(payload).encode(), "application/json")

    def _deny(self) -> None:
        self._send(HTTPStatus.FORBIDDEN, b"", "text/plain; charset=utf-8")

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _COMMON_HEADERS.items():
            self.send_header(name, value)
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(body)


class _FormHttpServer(ThreadingHTTPServer):
    """The server, carrying what the handlers need."""

    daemon_threads = True

    def __init__(self, conversation: Conversation, key: str) -> None:
        """Listen on the loopback address, on a free port.

        Args:
            conversation: The state the page reads and answers.
            key: What the page must send with every request.
        """
        super().__init__((FORM_HOST, 0), _Handler)
        self.conversation = conversation
        self.key = key
        port = self.server_address[1]
        self.allowed_hosts = frozenset({f"{FORM_HOST}:{port}", f"localhost:{port}"})


@dataclass(frozen=True, slots=True)
class SetupForm:
    """The running page: how to talk through it, and where it is."""

    io: FormIO
    url: str
    conversation: Conversation
    _server: _FormHttpServer

    def finish(self, *, ok: bool, message: str) -> None:
        """Show the ending on the page and leave it up long enough to be read."""
        self.conversation.finish(Outcome(ok, message))
        deadline = time.monotonic() + FORM_FAREWELL_SECONDS
        while time.monotonic() < deadline and not self.conversation.farewell_seen():
            time.sleep(FORM_WAIT_SLICE_SECONDS)

    def close(self) -> None:
        """Stop the server."""
        self._server.shutdown()
        self._server.server_close()


def open_setup_form(
    echo: Callable[[str], None], open_browser: Callable[[str], bool] = webbrowser.open
) -> SetupForm:
    """Start the page's server, open the page, and say where it is.

    Args:
        echo: Shows one line where the command was started.
        open_browser: Opens an address in the browser; ``False`` when it cannot.

    Returns:
        The running form. Call :meth:`SetupForm.close` when the set-up ends.
    """
    conversation = Conversation()
    key = secrets.token_urlsafe(FORM_KEY_BYTES)
    server = _FormHttpServer(conversation, key)
    threading.Thread(target=server.serve_forever, name="setup-form", daemon=True).start()
    url = f"http://{FORM_HOST}:{server.server_address[1]}/#{key}"
    echo(f"The set-up continues on a page in your browser: {url}")
    echo("If it did not open by itself, copy that address into your browser.")
    try:
        opened = open_browser(url)
    except webbrowser.Error:
        opened = False
    if not opened:
        echo("(No browser could be opened from here.)")
    return SetupForm(FormIO(conversation, echo), url, conversation, server)


def _first_int(values: list[str] | None) -> int:
    return _as_int(values[0]) if values else 0


def _as_int(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 0
