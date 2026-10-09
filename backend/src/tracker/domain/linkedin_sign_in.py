"""What signing in to LinkedIn with the owner's own developer application involves.

Plain values shared by the LinkedIn set-up step and the sign-in client; no
HTTP, no framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import SecretStr


class SignInProblem(StrEnum):
    """Why a LinkedIn sign-in did not end with a key, as far as the set-up must tell apart."""

    #: The owner clicked Cancel, or did not sign in to LinkedIn.
    CANCELLED = "cancelled"
    #: LinkedIn has not given the application the data portability product.
    PRODUCT_MISSING = "product_missing"
    #: LinkedIn refused the Client ID, the Client Secret or the redirect address.
    APP_DETAILS = "app_details"
    #: No answer came back before the owner stopped waiting.
    NO_ANSWER = "no_answer"
    #: Something else, such as a used-up code or a busy port.
    OTHER = "other"

    @property
    def needs_app_details_again(self) -> bool:
        """Whether a new try should ask for the Client ID and Client Secret again.

        LinkedIn shows a wrong Client ID or redirect address on its own page and
        never answers, so a missing answer points at them as much as a refusal does.
        """
        return self in {SignInProblem.APP_DETAILS, SignInProblem.NO_ANSWER}


@dataclass(frozen=True, slots=True)
class LinkedInApp:
    """The owner's LinkedIn developer application, from its Auth tab.

    Attributes:
        client_id: The application's public identifier.
        client_secret: The application's secret; never shown or logged.
    """

    client_id: str
    client_secret: SecretStr


@dataclass(frozen=True, slots=True)
class LinkedInGrant:
    """A key LinkedIn handed out after the owner allowed it.

    Attributes:
        access_token: The key the daily run reads LinkedIn with.
        expires_at: When it stops working, or ``None`` when LinkedIn did not say.
    """

    access_token: SecretStr
    expires_at: datetime | None
