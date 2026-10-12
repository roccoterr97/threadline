"""Making a mailbox's app password and collecting it.

The name it is given goes on the clipboard and the provider's page opens, on
the right account where the provider allows. Where the conversation can watch
the clipboard and the provider's password has a known shape, the password is
picked up as soon as it is copied; pasting it works all the while.

Google offers app passwords only once 2-Step Verification is on. Most people
have it on already, so the app-password page opens first; only when the
person answers that Google offers none does the page that switches it on open.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlencode

from tracker.services.setup.context import SetupContext
from tracker.shared.constants.mailbox import (
    APP_PASSWORD_NAME,
    IMAP_PRESETS,
    NO_APP_PASSWORD_ANSWERS,
    ImapPreset,
    ImapProvider,
)
from tracker.shared.errors import AppPasswordUnavailableError

#: What every provider has in common, in two plain sentences.
_APP_PASSWORD: Final[str] = (
    "Threadline signs in with an app password: a separate password just for "
    "Threadline, which you can remove at any time. Your normal password is never used."
)

#: What is particular to a provider, in one or two sentences.
_PROVIDER_NOTES: Final[dict[ImapProvider, str]] = {
    ImapProvider.ICLOUD: (
        "Apple calls it an app-specific password; two-factor authentication must be on. "
        "Sign in, then open Sign-In and Security > App-Specific Passwords."
    ),
    ImapProvider.YAHOO: (
        "On Yahoo's Account Security page, choose 'Create app password' under External connections."
    ),
    ImapProvider.FASTMAIL: (
        "Fastmail offers IMAP on paid plans above Basic. In Settings, open Privacy & "
        "Security > Manage app passwords and access, and choose Mail access."
    ),
    ImapProvider.CUSTOM: (
        "Your provider's help pages explain how to make one: search them for "
        "'app password' and 'IMAP'."
    ),
}

_NAME_ON_CLIPBOARD: Final[str] = (
    f"The name '{APP_PASSWORD_NAME}' is on your clipboard: paste it as the app name."
)
_NAME_TO_TYPE: Final[str] = f"Name it '{APP_PASSWORD_NAME}' when the page asks for a name."
_COPY_IT: Final[str] = (
    "Copy the 16-letter password {company} shows; the set-up picks it up by itself."
)
_SAY_IF_NONE: Final[str] = "If {company} says the setting is not available, answer no below."
_TURN_ON_TWO_STEP: Final[str] = (
    "{company} asks you to turn on 2-Step Verification first: it texts or prompts "
    "your phone, about 5 minutes. Then come back."
)
_TWO_STEP_ON: Final[str] = "Once 2-Step Verification is on"
_WAITING_PROMPT: Final[str] = "Waiting for the copied password, or paste it here (it is not shown)"
_PASTE_PROMPT: Final[str] = "Paste the {label} app password (it is not shown)"
_PICKED_UP: Final[str] = "Picked up the password from your clipboard."
_PICKED_UP_AND_EMPTIED: Final[str] = (
    "Picked up the password from your clipboard, and emptied the clipboard."
)
_NONE_OFFERED: Final[str] = (
    "{company} offers no app passwords for this account. On a work or school "
    "account the administrator may have switched them off"
)


def page_address(page: str, preset: ImapPreset, address: str) -> str:
    """Name the owner's account on a provider's page, where the provider allows it.

    Args:
        page: The page's address.
        preset: The provider.
        address: The mailbox's address.

    Returns:
        The page with the account named, or unchanged when the provider has no
        such parameter or the sign-in name is not an address.
    """
    if not preset.account_parameter or "@" not in address:
        return page
    return f"{page}?{urlencode({preset.account_parameter: address})}"


class AppPasswordQuestion:
    """Opens the page where the app password is made, and asks for the password."""

    def __init__(self, ctx: SetupContext, provider: ImapProvider, address: str) -> None:
        """Prepare the question for one mailbox.

        Args:
            ctx: The set-up's context.
            provider: The mailbox's provider.
            address: The name the mailbox signs in with, usually its address.
        """
        self._ctx = ctx
        self._provider = provider
        self._preset = IMAP_PRESETS[provider]
        self._address = address
        self._watching = False
        self._two_step_shown = False

    def explain(self) -> None:
        """Say what an app password is, and what is particular to this provider."""
        self._ctx.io.say(_APP_PASSWORD)
        note = _PROVIDER_NOTES.get(self._provider)
        if note is not None:
            self._ctx.io.say(note)

    def open_page(self) -> None:
        """Put the name on the clipboard, open the page and say how the password comes back."""
        preset, io = self._preset, self._ctx.io
        if not preset.app_password_page:
            return
        io.say(_NAME_ON_CLIPBOARD if io.copy(APP_PASSWORD_NAME) else _NAME_TO_TYPE)
        io.open_page(page_address(preset.app_password_page, preset, self._address))
        self._watching = bool(preset.copied_password_pattern) and io.watches_clipboard()
        if self._watching:
            io.say(_COPY_IT.format(company=preset.company))
        if preset.two_step_page:
            io.say(_SAY_IF_NONE.format(company=preset.company))

    def ask(self) -> str:
        """Ask for the password once, opening two-step sign-in first when none is offered.

        Returns:
            What was copied, pasted or typed, unchecked. Never shown.

        Raises:
            AppPasswordUnavailableError: If the provider still offers none once
                two-step sign-in was shown.
        """
        answer = self._answer()
        if not self._preset.two_step_page or not _means_none_offered(answer):
            return answer
        if self._two_step_shown:
            raise AppPasswordUnavailableError(_NONE_OFFERED.format(company=self._preset.company))
        self._two_step_shown = True
        self._turn_on_two_step()
        return self.ask()

    def _answer(self) -> str:
        """Pick the password up from the clipboard or take it pasted, emptying the clipboard."""
        io = self._ctx.io
        if not self._watching:
            return io.ask_secret(_PASTE_PROMPT.format(label=self._preset.label))
        answer = io.ask_secret_or_copied(_WAITING_PROMPT, self._looks_copied)
        if answer.copied:
            io.say(_PICKED_UP_AND_EMPTIED if io.copy("") else _PICKED_UP)
        return answer.value

    def _looks_copied(self, text: str) -> bool:
        """Whether the clipboard holds what this provider's app password looks like."""
        return re.fullmatch(self._preset.copied_password_pattern, text.strip()) is not None

    def _turn_on_two_step(self) -> None:
        """Open the page that switches two-step sign-in on, then the app-password page again."""
        preset, io = self._preset, self._ctx.io
        io.say(_TURN_ON_TWO_STEP.format(company=preset.company))
        io.open_page(page_address(preset.two_step_page, preset, self._address))
        io.pause(_TWO_STEP_ON)
        self.open_page()


def _means_none_offered(answer: str) -> bool:
    """Whether the answer says the provider offers no app passwords."""
    return " ".join(answer.lower().split()) in NO_APP_PASSWORD_ANSWERS
