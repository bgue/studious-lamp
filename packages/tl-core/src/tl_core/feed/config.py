"""Feed settings: ``feed.reactions.enabled`` and ``feed.signal_tags`` (brief 30.5; P0-I8 D2).

Every reader goes through these two functions, which read the settings in force for a scope inside
the caller's transaction: a change applies to the next call, with no restart, and the company
value reaches every project that does not set its own.
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

SIGNAL_TAGS_KEY = "feed.signal_tags"
REACTIONS_KEY = "feed.reactions.enabled"


def signal_tags(conn: Connection, scope: str) -> tuple[str, ...]:
    """The signal tag set for ``scope`` (lower case words without the sigil)."""
    found = value_of(conn, SIGNAL_TAGS_KEY, project=project_of_scope(scope))
    return tuple(str(word).lower() for word in found)


def reactions_enabled(conn: Connection, scope: str) -> bool:
    """Whether ``Feed.Reacted`` is accepted in ``scope``."""
    return bool(value_of(conn, REACTIONS_KEY, project=project_of_scope(scope)))
