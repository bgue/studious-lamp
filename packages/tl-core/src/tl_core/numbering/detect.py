"""Key detection: find record keys in free text and resolve them to records (brief 7.2).

"Any recognisable key typed in a field, post, thread message, or correspondence body becomes a
suggestion chip; Tab accepts it inline." Recognisable means: it matches a numbering pattern that
applies to the scope. ``detect_keys`` is pure text work; ``resolve_chips`` looks the keys up so a
client can colour the chip and offer to link.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import text

from tl_core.numbering.config import NumberingPattern, get_numbering
from tl_core.uow import UnitOfWork

_LOOKUP_SQL = text(
    "SELECT id, scope, type, title, status, voided FROM cur_core_record "
    "WHERE key = :key AND scope IN (:scope, 'company')"
)
_LINKED_SQL = text(
    "SELECT status FROM cur_links WHERE status <> 'retracted' AND "
    "((from_id = :a AND to_id = :b) OR (from_id = :b AND to_id = :a))"
)
_RANK = {"active": 0, "stale": 1, "broken": 2, "suggested": 3}


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
    candidates: list[tuple[KeyMatch, int]] = []
    for index, pattern in enumerate(patterns):
        compiled = pattern.compiled()
        for m in compiled.search_regex().finditer(text_):
            if compiled.parse(m.group(0)) is None:
                continue
            candidates.append(
                (
                    KeyMatch(start=m.start(), end=m.end(), key=m.group(0), pattern_id=pattern.id),
                    index,
                )
            )

    candidates.sort(key=lambda c: (-(c[0].end - c[0].start), c[1], c[0].start))
    kept: list[KeyMatch] = []
    for match, _ in candidates:
        overlaps = any(not (match.end <= k.start or match.start >= k.end) for k in kept)
        if not overlaps:
            kept.append(match)
    return sorted(kept, key=lambda k: k.start)


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
    chips: list[KeyChip] = []
    for match in matches:
        rows = uow.conn().execute(_LOOKUP_SQL, {"key": match.key, "scope": scope}).all()
        ordered = sorted(rows, key=lambda r: bool(r.scope != scope))
        found = ordered[0] if ordered else None
        if found is not None and found.id == exclude_id:
            continue

        link_status: str | None = None
        if found is not None and linked_to is not None:
            link_rows = uow.conn().execute(_LINKED_SQL, {"a": linked_to, "b": found.id}).all()
            statuses = [str(r.status) for r in link_rows]
            if statuses:
                link_status = min(statuses, key=lambda s: _RANK[s])

        chips.append(
            KeyChip(
                start=match.start,
                end=match.end,
                key=match.key,
                pattern_id=match.pattern_id,
                record_id=found.id if found is not None else None,
                record_type=found.type if found is not None else None,
                title=found.title if found is not None else None,
                status=found.status if found is not None else None,
                voided=bool(found.voided) if found is not None else False,
                link_status=link_status,
            )
        )
    return chips


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
    applicable = patterns if patterns is not None else get_numbering().for_scope(scope)
    return resolve_chips(
        uow,
        scope,
        detect_keys(text_, applicable),
        linked_to=linked_to,
        exclude_id=linked_to,
    )
