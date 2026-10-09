"""Fixed facts about signing in to LinkedIn with the owner's own developer application.

The set-up makes the LinkedIn key with LinkedIn's ordinary sign-in (the OAuth
2.0 authorization-code flow): it opens LinkedIn's consent page for the owner's
application, catches LinkedIn's answer on this computer and trades it for the
key. None of it is a secret or differs between machines, so it is code rather
than configuration.

Sources: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
and https://learn.microsoft.com/en-us/linkedin/shared/authentication/token-introspection
"""

from __future__ import annotations

from typing import Final

#: LinkedIn's consent page, where the owner clicks "Allow".
AUTHORIZATION_URL: Final[str] = "https://www.linkedin.com/oauth/v2/authorization"

#: Where the one-time code from the consent page is traded for the key.
ACCESS_TOKEN_URL: Final[str] = "https://www.linkedin.com/oauth/v2/accessToken"

#: Where a key's expiry is read, with the application's Client ID and Secret.
INTROSPECT_URL: Final[str] = "https://www.linkedin.com/oauth/v2/introspectToken"

#: The permission the "Member Data Portability API (Member)" product grants,
#: as LinkedIn's page for that product names it.
SCOPE: Final[str] = "r_dma_portability_self_serve"

#: The port LinkedIn's answer arrives on. It is fixed because the owner types
#: the whole address once on the application's Auth tab, and LinkedIn only
#: sends answers to an address typed there exactly.
CALLBACK_PORT: Final[int] = 8746

#: The path LinkedIn's answer arrives on.
CALLBACK_PATH: Final[str] = "/linkedin"

#: The address the owner adds on the Auth tab, and the one sent to LinkedIn.
REDIRECT_URL: Final[str] = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

#: Where the one-time listener listens: this computer only. ``localhost`` can
#: mean either, depending on the browser, so both are tried; the second is
#: optional because not every computer has IPv6.
CALLBACK_ADDRESSES: Final[tuple[str, ...]] = ("127.0.0.1", "::1")

#: How long to wait for LinkedIn's answer before asking whether to keep waiting.
#: Signing in with a second step (a code by text message) fits well within it.
WAIT_SLICE_SECONDS: Final[float] = 120.0

#: How often the wait looks whether the answer has arrived.
POLL_SECONDS: Final[float] = 0.2

#: How often the listener looks whether it has been told to stop, so the port
#: is given back at once when the sign-in ends.
STOP_POLL_SECONDS: Final[float] = 0.05

#: Random bytes in the ``state`` that ties LinkedIn's answer to this sign-in.
STATE_BYTES: Final[int] = 32

#: Name under which the application's Client Secret is kept in the encrypted store.
CLIENT_SECRET_NAME: Final[str] = "linkedin_client_secret"

#: The ``.env`` setting holding the application's Client ID. It is used on this
#: computer only, to renew the key, and is never copied to GitHub or the cloud.
CLIENT_ID_SETTING: Final[str] = "LINKEDIN_CLIENT_ID"

#: Errors LinkedIn sends back when the owner cancelled or did not sign in.
CANCELLED_ERRORS: Final[frozenset[str]] = frozenset(
    {"user_cancelled_authorize", "user_cancelled_login"}
)

#: Errors LinkedIn sends back when the application lacks the permission asked for.
SCOPE_ERRORS: Final[frozenset[str]] = frozenset({"unauthorized_scope_error", "invalid_scope"})

#: Errors the key exchange answers when the Client ID, Secret or address is wrong.
APP_DETAIL_ERRORS: Final[frozenset[str]] = frozenset({"invalid_client", "invalid_redirect_uri"})

#: Longest stretch of LinkedIn's own error wording that is shown to the owner.
ERROR_DESCRIPTION_MAX_CHARACTERS: Final[int] = 200
