"""The scan-card contract harness (P2-QR T03; contract in ``tl_core.qr.types``).

``check_scan_card_contract(provider, conn, ...)`` proves that a status-card provider keeps the S1
contract: it satisfies the ``ScanCardProvider`` protocol, names a dotted view word, answers a card
of its own record type for a visible record, answers ``None`` for a hidden record (and a card for
the privileged viewer), answers ``None`` without raising for garbage ids, and writes nothing.

It imports no test framework: a broken rule raises :class:`ScanCardContractViolation` (an
``AssertionError``), and the message names the rule with one of the words ``protocol``,
``view_word``, ``visible``, ``record_type``, ``hidden``, ``raised`` or ``write``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, event
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.qr.types import ScanCard, ScanCardProvider

_VIEW_WORD = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
_WRITE_WORDS = ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER")
#: Ids that must answer None without raising: empty, over-long, and a well-formed miss.
_GARBAGE_IDS = ("", "x" * 300, "00000000000000000000000000")


class ScanCardContractViolation(AssertionError):  # noqa: N818  (the name is the contract's)
    """A scan-card provider broke a rule of the contract; the message names the rule."""


def _card_or_raise(
    provider: ScanCardProvider,
    conn: Connection,
    record_id: str,
    viewer: Viewer,
    now: datetime,
    rule: str,
) -> ScanCard | None:
    try:
        return provider.card(conn, record_id, viewer, now)
    except Exception as exc:
        raise ScanCardContractViolation(
            f"scan card provider {provider.record_type!r}: {rule}: card raised {type(exc).__name__}"
        ) from exc


def check_scan_card_contract(
    provider: object,
    conn: Connection,
    *,
    visible_id: str,
    hidden_id: str,
    privileged: Viewer,
    now: datetime,
) -> ScanCard:
    """Raise :class:`ScanCardContractViolation` unless ``provider`` keeps the contract.

    Returns the card of the visible check.
    """
    if not isinstance(provider, ScanCardProvider):
        raise ScanCardContractViolation(
            "scan card provider: protocol: it lacks record_type, view_word or card"
        )
    name = provider.record_type

    word: Any = provider.view_word
    if not isinstance(word, str) or _VIEW_WORD.fullmatch(word) is None:
        raise ScanCardContractViolation(
            f"scan card provider {name!r}: view_word must be a dotted word, got {word!r}"
        )

    statements: list[str] = []

    def watch(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        statements.append(statement)

    event.listen(conn, "before_cursor_execute", watch)
    try:
        card = _card_or_raise(provider, conn, visible_id, LOWEST, now, "visible")
        if card is None:
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: visible: no card for a visible record"
            )
        if card.record_type != name:
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: record_type: the card names {card.record_type!r}"
            )
        if card.as_of.tzinfo is None or card.as_of.utcoffset() is None:
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: visible: as_of must be timezone aware"
            )

        if _card_or_raise(provider, conn, hidden_id, LOWEST, now, "hidden") is not None:
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: hidden: a card for a hidden record"
            )
        if _card_or_raise(provider, conn, hidden_id, privileged, now, "hidden") is None:
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: hidden: the privileged viewer gets no card"
            )

        for garbage in _GARBAGE_IDS:
            if _card_or_raise(provider, conn, garbage, LOWEST, now, "raised") is not None:
                raise ScanCardContractViolation(
                    f"scan card provider {name!r}: raised: a card for an id that is not a record"
                )
    finally:
        event.remove(conn, "before_cursor_execute", watch)

    for statement in statements:
        if statement.lstrip().upper().startswith(_WRITE_WORDS):
            raise ScanCardContractViolation(
                f"scan card provider {name!r}: write: a card call wrote data"
            )
    return card
