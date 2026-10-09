"""The relation vocabulary of links (brief 7.1): codes, labels, inverses, and per-type defaults.

A relation has a forward code (``raised_against``) and an inverse code (``has_raised``). A link is
always stored in the forward direction; the inverse code and label only describe the same link
as seen from the other record. The vocabulary is extensible: ``RelationVocabulary.add`` registers
a company or module relation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, get_args

from tl_core.services.errors import UnknownRelationError

LinkSource = Literal[
    "manual",
    "key_detected",
    "tray",
    "bulk",
    "model_selection",
    "thread_dispatch",
    "rule",
    "enricher",
    "import",
    "mapping",
]
LINK_SOURCES: tuple[LinkSource, ...] = get_args(LinkSource)
Direction = Literal["out", "in"]

#: Used when no per-type-pair default applies.
DEFAULT_RELATION = "references"
_CODE = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class Relation:
    code: str
    label: str
    inverse_code: str
    inverse_label: str

    @property
    def symmetric(self) -> bool:
        """True when the relation reads the same from both ends (``same_as``)."""
        return self.code == self.inverse_code


class RelationVocabulary:
    """Relations by code, in insertion order. Forward and inverse codes are all distinct."""

    def __init__(self, relations: Iterable[Relation] = ()) -> None:
        self._relations: dict[str, Relation] = {}
        self._inverses: dict[str, Relation] = {}
        for relation in relations:
            self.add(relation)

    def add(self, relation: Relation) -> None:
        """Register a relation. Raises ``ValueError`` for a malformed or already used code."""
        codes = {relation.code, relation.inverse_code}
        for code in sorted(codes):
            if _CODE.fullmatch(code) is None:
                raise ValueError(f"relation code {code!r} must match [a-z][a-z0-9_]*")
        taken = set(self._relations) | set(self._inverses)
        clashing = sorted(codes & taken)
        if clashing:
            raise ValueError(f"relation code already in the vocabulary: {', '.join(clashing)}")
        self._relations[relation.code] = relation
        self._inverses[relation.inverse_code] = relation

    def codes(self) -> list[str]:
        """Forward codes in insertion order."""
        return list(self._relations)

    def __contains__(self, code: object) -> bool:
        """True for a forward code. An inverse code is not a member."""
        return isinstance(code, str) and code in self._relations

    def get(self, code: str) -> Relation:
        """The relation with this forward code.

        Raises ``UnknownRelationError``. When ``code`` is an inverse code the message names the
        forward relation to use with the two ends swapped.
        """
        if code in self._relations:
            return self._relations[code]
        if code in self._inverses:
            forward = self._inverses[code].code
            raise UnknownRelationError(
                f"{code!r} is the inverse of {forward!r}; "
                f"use {forward!r} with the two records swapped"
            )
        raise UnknownRelationError(f"unknown relation {code!r}")

    def resolve(self, code: str) -> tuple[Relation, bool]:
        """The relation for a forward or an inverse code, and whether the code was the inverse.

        For a symmetric relation the code is its own inverse and the flag is ``False``.
        Raises ``UnknownRelationError`` for an unknown code.
        """
        if code in self._relations:
            return self._relations[code], False
        if code in self._inverses:
            return self._inverses[code], True
        raise UnknownRelationError(f"unknown relation {code!r}")

    def label(self, code: str, direction: Direction) -> str:
        """How the link reads from a record: ``out`` is the label, ``in`` the inverse label."""
        relation = self.get(code)
        return relation.label if direction == "out" else relation.inverse_label


DEFAULT_RELATIONS: tuple[Relation, ...] = (
    Relation("references", "references", "referenced_by", "referenced by"),
    Relation("derived_from", "derived from", "source_of", "source of"),
    Relation("supersedes", "supersedes", "superseded_by", "superseded by"),
    Relation("responds_to", "responds to", "responded_by", "responded by"),
    Relation("raised_against", "raised against", "has_raised", "has raised"),
    Relation("resolves", "resolves", "resolved_by", "resolved by"),
    Relation("belongs_to", "belongs to", "contains", "contains"),
    Relation("requires", "requires", "required_by", "required by"),
    Relation("blocks", "blocks", "blocked_by", "blocked by"),
    Relation("verifies", "verifies", "verified_by", "verified by"),
    Relation("dispatched_from", "dispatched from", "dispatched", "dispatched"),
    Relation("attached_to", "attached to", "has_attachment", "has attachment"),
    Relation("same_as", "same as", "same_as", "same as"),
)

#: Default relation per (from type, to type). Illustrative until modules register their types.
DEFAULT_PAIR_RELATIONS: Mapping[tuple[str, str], str] = {
    ("piping.Weld", "quality.NCR"): "raised_against",
}


def default_vocabulary() -> RelationVocabulary:
    """A new vocabulary holding the thirteen relations of brief 7.1."""
    return RelationVocabulary(DEFAULT_RELATIONS)


def default_relation(
    from_type: str, to_type: str, pairs: Mapping[tuple[str, str], str] | None = None
) -> str:
    """The relation to pre-select when linking ``from_type`` to ``to_type``.

    Lookup order in ``pairs`` (default ``DEFAULT_PAIR_RELATIONS``): the exact pair, then
    ``(from_type, "*")``, then ``("*", to_type)``, then ``DEFAULT_RELATION``.
    """
    table = DEFAULT_PAIR_RELATIONS if pairs is None else pairs
    for key in ((from_type, to_type), (from_type, "*"), ("*", to_type)):
        if key in table:
            return table[key]
    return DEFAULT_RELATION


__all__ = [
    "DEFAULT_PAIR_RELATIONS",
    "DEFAULT_RELATION",
    "DEFAULT_RELATIONS",
    "LINK_SOURCES",
    "Direction",
    "LinkSource",
    "Relation",
    "RelationVocabulary",
    "UnknownRelationError",
    "default_relation",
    "default_vocabulary",
]
