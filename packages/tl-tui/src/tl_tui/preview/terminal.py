"""Which inline-image protocol the terminal speaks, from the environment alone (brief SCOPE §4).

The function never queries the terminal and never imports an image library. Rules are applied in
order and the first match wins.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

ImageProtocol = Literal["kitty", "iterm2", "sixel", "none"]


def image_protocol(env: Mapping[str, str]) -> ImageProtocol:
    """Return the page-1 image protocol: ``kitty``, ``iterm2``, ``sixel`` or ``none``."""
    if "TL_IMAGES" in env:
        forced = env["TL_IMAGES"]
        if forced == "kitty":
            return "kitty"
        if forced == "iterm2":
            return "iterm2"
        if forced == "sixel":
            return "sixel"
        return "none"
    term = env.get("TERM", "")
    if term == "dumb" or "TMUX" in env or "STY" in env:
        return "none"
    if "KITTY_WINDOW_ID" in env or term == "xterm-kitty" or env.get("TERM_PROGRAM") == "ghostty":
        return "kitty"
    if env.get("TERM_PROGRAM") in ("iTerm.app", "WezTerm"):
        return "iterm2"
    if "WT_SESSION" in env or "sixel" in term or term.startswith(("foot", "mlterm")):
        return "sixel"
    return "none"
