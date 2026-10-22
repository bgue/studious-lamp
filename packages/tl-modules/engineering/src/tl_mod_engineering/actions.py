"""Which commands the viewer may run on a tag now (P1-UX2-S1).

``RULES`` is the one source of the access level and the label of each command, and ``ENDED`` of the
workflow states in which a tag has left service for good (``handlers.tags`` and ``imports.apply``
read it, so the offer and the refusal cannot drift). A test holds each rule's level equal to the
``access`` of ``commands.API_COMMANDS``. The hook ``tag_actions`` is a pure function of the tag's
own row and ``holds``.

An offer is advice; the handler still checks the new number, the class and the reason when the
command runs. Commands that need no record (create a tag) are not offers. Splitting a tag is a
command line act (``SplitTag`` answers with several results) and is not offered.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection
from tl_core.actions import ActionOffer, Holds, Level

from tl_mod_engineering import registry

#: Workflow states in which a tag has left service for good: it takes no more changes.
ENDED = ("Superseded", "Deleted")


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer on a tag that is still in service."""

    command: str  # the command model's class name, as in ``commands.API_COMMANDS``
    label: str  # plain words
    level: Level


RULES: tuple[Rule, ...] = (
    Rule("ReclassifyTag", "Change class", "user"),
    Rule("RenameTag", "Rename", "user"),
    Rule("MergeTags", "Merge into another tag", "user"),
)


def tag_actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this tag now: none once it is superseded or deleted
    (a voided tag is not read at all, as for the handlers)."""
    tag = registry.get_tag(conn, record_id)
    if tag is None or tag.status in ENDED:
        return []
    return [
        ActionOffer(command=rule.command, label=rule.label) for rule in RULES if holds(rule.level)
    ]


__all__ = ["ENDED", "RULES", "Rule", "tag_actions"]
