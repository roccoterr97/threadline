"""Tuning values for the "same person?" questions the linker asks."""

from __future__ import annotations

from typing import Final

#: Most named colleagues one bare address is asked about. ``alex@`` at a fund
#: with two Alexes is worth two questions; an address that fits a whole team
#: says too little to be worth any.
MAX_QUESTIONS_PER_ADDRESS: Final[int] = 3
