"""How a value the user typed is quoted back in a message (P0-I8)."""

from __future__ import annotations

MAX_SHOWN = 80


def shown(value: object, limit: int = MAX_SHOWN) -> str:
    """``repr(value)`` cut to ``limit`` characters with an ellipsis, so a message never echoes a
    5,000-digit number or a page of text back in full."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
