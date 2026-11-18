"""What the signed-in entry points read of the intake queue (V3-F4): the three reads and the words.

One place for the route, the embedded client and ``tl intake``, so they cannot differ. The items
need ``forms.intake.review`` and the codes ``forms.intake.issue``, on the project, checked before
any read (a person without the word is refused the same for every id). The reads are the views' own,
as the caller's viewer: a hidden item and a missing one are the same ``None``, and ``MSG_ITEM`` is
the one text for both. An item's answers are returned by ``item_detail`` alone, for a Pending item
the viewer may read; a list, an error and a report carry no answer, no body, no salt, no code and no
code hash (the views name their columns one by one and hold none of them).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word

from tl_mod_forms import MODULE, intake_views
from tl_mod_forms.names import INTAKE_ISSUE, INTAKE_REVIEW

#: The one text for an item that is missing, hidden, of another project or already purged.
MSG_ITEM: Final = "no such intake item"


@dataclass(frozen=True)
class ItemDetail:
    """An item as the queue shows it, and for a Pending one the sender's answers."""

    row: intake_views.ItemRow
    answers: list[dict[str, Any]] | None


@dataclass(frozen=True)
class IntakeCodeRow(intake_views.CodeRow):
    """A code row under a name of its own: the route's schema is not another module's ``CodeRow``
    (the OpenAPI component names are the class names)."""


def code_page(
    conn: Connection,
    scope: str,
    *,
    state: str | None,
    limit: int,
    offset: int,
    viewer: confidentiality.Viewer,
) -> intake_views.Page[IntakeCodeRow]:
    """``intake_views.code_list`` with each row as an ``IntakeCodeRow``."""
    page = intake_views.code_list(
        conn, scope, state=state, limit=limit, offset=offset, viewer=viewer
    )
    return intake_views.Page(rows=[IntakeCodeRow(**asdict(r)) for r in page.rows], total=page.total)


def require_issue(conn: Connection, actor: str, scope: str) -> None:
    """``forms.intake.issue`` on ``scope`` (codes); ``ForbiddenError`` otherwise."""
    _require(conn, actor, scope, INTAKE_ISSUE)


def require_review(conn: Connection, actor: str, scope: str) -> None:
    """``forms.intake.review`` on ``scope`` (items); ``ForbiddenError`` otherwise."""
    _require(conn, actor, scope, INTAKE_REVIEW)


def _require(conn: Connection, actor: str, scope: str, word: str) -> None:
    require_word(
        conn,
        holder_for_actor(conn, actor),
        scope=scope,
        module=MODULE,
        word=normalise_word(word),
        what=word,
    )


def item_detail(
    conn: Connection, scope: str, item_id: str, viewer: confidentiality.Viewer
) -> ItemDetail | None:
    """The item and, when Pending, its answers; ``None`` for a missing or hidden item."""
    row = intake_views.item_detail(conn, scope, item_id, viewer=viewer)
    if row is None:
        return None
    return ItemDetail(
        row=row, answers=intake_views.item_answers(conn, scope, item_id, viewer=viewer)
    )


__all__ = [
    "MSG_ITEM",
    "IntakeCodeRow",
    "ItemDetail",
    "code_page",
    "item_detail",
    "require_issue",
    "require_review",
]
