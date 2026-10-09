"""Key detection: find record keys in free text and resolve them to records (brief 7.2).

"Any recognisable key typed in a field, post, thread message, or correspondence body becomes a
suggestion chip; Tab accepts it inline." Recognisable means: it matches a numbering pattern that
applies to the scope. ``detect_keys`` is pure text work; ``resolve_chips`` looks the keys up so a
client can colour the chip and offer to link.

STUB (P0-I3-T07): the models and signatures are final; the three bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from tl_core.numbering.config import NumberingPattern
from tl_core.uow import UnitOfWork


class KeyMatch(BaseModel):
    start: int  # offset of the first character in the text
    end: int  # offset just past the last character
    key: str
    pattern_id: str


class KeyChip(BaseModel):
    """A detected key and what it refers to."""

    start: int
    end: int
    key: str
    pattern_id: str
    record_id: str | None  # None when no record has this key
    record_type: str | None = None
    title: str | None = None
    status: str | None = None
    voided: bool = False
    # Status of the live link between ``linked_to`` and this record (any direction or relation),
    # or None when not linked or when no ``linked_to`` was given.
    link_status: str | None = None


def detect_keys(text_: str, patterns: Sequence[NumberingPattern]) -> list[KeyMatch]:
    """Keys in ``text_`` that fit one of ``patterns``, in text order, never overlapping.

    Only keys spelled as the pattern writes them count (``P1-REC-0012``, not ``P1-REC-00012``),
    and a key must not be glued to other letters, digits, underscores or dashes. When two matches
    overlap the longer wins, then the one from the earlier pattern. The same key twice in the text
    gives two matches.
    """
    raise NotImplementedError


def resolve_chips(
    uow: UnitOfWork,
    scope: str,
    matches: Sequence[KeyMatch],
    *,
    linked_to: str | None = None,
    exclude_id: str | None = None,
) -> list[KeyChip]:
    """Look each match up in ``cur_core_record`` and build chips, in the order given.

    A key is looked up in ``scope`` first, then in ``company``. A key no record has gives a chip
    with ``record_id=None``. Matches that resolve to ``exclude_id`` (the record being edited) are
    dropped. With ``linked_to`` the chip carries the status of the live (not retracted) link between
    that record and the chip's record, in either direction.
    """
    raise NotImplementedError


def suggest_chips(
    uow: UnitOfWork,
    scope: str,
    text_: str,
    *,
    linked_to: str | None = None,
    patterns: Sequence[NumberingPattern] | None = None,
) -> list[KeyChip]:
    """Detect keys in ``text_`` with the patterns that apply to ``scope`` and resolve them.

    ``patterns`` defaults to ``get_numbering().for_scope(scope)``. ``linked_to`` is both the record
    to test links against and the record to leave out of the result (a record is not suggested to
    link to itself).
    """
    raise NotImplementedError
