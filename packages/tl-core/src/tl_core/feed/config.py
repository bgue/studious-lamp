"""Feed settings as Phase 0 constants (FANOUT decision D7).

``feed.signal_tags`` and ``feed.reactions.enabled`` (brief 30) become about:config settings in
P0-I8. Until then every reader goes through these two functions, so the swap is one edit.
"""

from __future__ import annotations

from tl_core.feed.types import DEFAULT_SIGNAL_TAGS

REACTIONS_ENABLED = True


def signal_tags() -> tuple[str, ...]:
    """The signal tag set (lower case words without the sigil)."""
    return DEFAULT_SIGNAL_TAGS


def reactions_enabled() -> bool:
    """Whether ``Feed.Reacted`` is accepted."""
    return REACTIONS_ENABLED
