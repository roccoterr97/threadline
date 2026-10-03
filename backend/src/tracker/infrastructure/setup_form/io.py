"""The set-up's conversation through the page, echoed in plain lines where it was started."""

from __future__ import annotations

from collections.abc import Callable

import typer

from tracker.infrastructure.setup_form.conversation import NO, YES, Conversation, QuestionKind
from tracker.infrastructure.terminal_io import copy_to_clipboard


class FormIO:
    """Asks on the page; says every line on the page and where the command runs.

    The echo carries no answers, only what was said and asked, so whoever
    started the command (a person, or Claude Code following the set-up recipe)
    can follow along without ever seeing a key.
    """

    def __init__(
        self, conversation: Conversation, echo: Callable[[str], None] = typer.echo
    ) -> None:
        """Bind the conversation to its page.

        Args:
            conversation: The state the page reads and answers.
            echo: Shows one line where the command was started.
        """
        self._conversation = conversation
        self._echo = echo

    def say(self, text: str) -> None:
        """Show one line."""
        self._conversation.say(text)
        self._echo(text)

    def ask(self, prompt: str, *, default: str | None = None) -> str:
        """Ask for a value that may be shown on screen."""
        self._echo(f"? {prompt}")
        answer = self._conversation.ask(QuestionKind.TEXT, prompt, default)
        return answer if answer else (default or "")

    def ask_secret(self, prompt: str) -> str:
        """Ask for a value in a hidden field; it is never echoed."""
        self._echo(f"? {prompt}")
        return self._conversation.ask(QuestionKind.SECRET, prompt)

    def confirm(self, prompt: str, *, default: bool) -> bool:
        """Ask a yes/no question."""
        self._echo(f"? {prompt}")
        answer = self._conversation.ask(QuestionKind.CONFIRM, prompt, YES if default else NO)
        if answer == YES:
            return True
        if answer == NO:
            return False
        return default

    def pause(self, prompt: str) -> None:
        """Wait until the person clicks Continue."""
        self._echo(f"? {prompt}")
        self._conversation.ask(QuestionKind.CONTINUE, prompt)

    def open_page(self, url: str) -> None:
        """Offer the page as a link; the browser is already showing the set-up."""
        self._conversation.link(url)
        self._echo(f"  Open {url}")

    def copy(self, value: str) -> bool:
        """Put a value on the clipboard, when this machine has one."""
        return copy_to_clipboard(value)
