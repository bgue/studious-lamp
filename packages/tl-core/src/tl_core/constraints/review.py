"""Constraint review groups (P2-I2-T04a2): a pure grouping of an already-read list of views.

No SQL, no clock, no viewer: the caller reads the list (``queries.list_constraints``) and passes
it in. A group carries keys only, never description text. ``owner`` groups by ``view.owner``
with ``-`` for none (that group sorts last); ``category`` groups by ``view.category``; ``age``
groups by the band of ``view.age_days`` and keeps every band, empty ones with count 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from tl_core.constraints.queries import ConstraintView

AGE_BANDS: Final = (("0-7", 0, 7), ("8-14", 8, 14), ("15-28", 15, 28), ("29+", 29, None))
BY_WORDS: Final = ("owner", "category", "age")
_UNOWNED: Final = "-"


@dataclass(frozen=True)
class ConstraintGroup:
    label: str
    count: int
    blocking: int
    aging: int
    keys: tuple[str, ...]  # keys in key order


def _band(age_days: int) -> str:
    for label, _low, high in AGE_BANDS:
        if high is None or age_days <= high:
            return label
    raise AssertionError("AGE_BANDS covers every age")  # pragma: no cover


def _label(view: ConstraintView, by: str) -> str:
    if by == "owner":
        return view.owner or _UNOWNED
    if by == "category":
        return view.category
    return _band(view.age_days)


def _group(label: str, views: list[ConstraintView]) -> ConstraintGroup:
    ordered = sorted(views, key=lambda v: v.key)
    return ConstraintGroup(
        label=label,
        count=len(ordered),
        blocking=sum(1 for v in ordered if v.severity == "blocking"),
        aging=sum(1 for v in ordered if v.aging),
        keys=tuple(v.key for v in ordered),
    )


def review_groups(views: Sequence[ConstraintView], by: str) -> list[ConstraintGroup]:
    """Group ``views`` by ``owner``, ``category`` or ``age``; ``by`` outside ``BY_WORDS`` raises."""
    if by not in BY_WORDS:
        raise ValueError(f"by must be one of {', '.join(BY_WORDS)}")
    buckets: dict[str, list[ConstraintView]] = {}
    if by == "age":
        buckets = {label: [] for label, _low, _high in AGE_BANDS}
    for view in views:
        buckets.setdefault(_label(view, by), []).append(view)
    if by == "age":
        return [_group(label, buckets[label]) for label, _low, _high in AGE_BANDS]
    labels = sorted(buckets, key=lambda label: (label == _UNOWNED and by == "owner", label))
    return [_group(label, buckets[label]) for label in labels]
