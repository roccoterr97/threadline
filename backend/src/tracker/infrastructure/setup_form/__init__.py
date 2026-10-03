"""The set-up's conversation on a page in the browser, served to this computer only.

The wizard asks its questions through :class:`FormIO`; a small local web
server shows them on a page where the person types the answers, with keys in
hidden fields instead of a terminal prompt. Nothing leaves the machine.
"""

from __future__ import annotations

from tracker.infrastructure.setup_form.io import FormIO
from tracker.infrastructure.setup_form.server import SetupForm, open_setup_form

__all__ = ["FormIO", "SetupForm", "open_setup_form"]
