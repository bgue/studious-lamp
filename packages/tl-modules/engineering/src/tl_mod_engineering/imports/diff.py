"""Comparing a tag list with the tags a project holds (brief 9 M2; P1-I1-T10b).

``plan_import`` is pure: it reads ``ImportRow`` values (``mapping.read_rows``) and ``ExistingTag``
values and returns an ``ImportPlan``. A row that is blank in the file leaves the tag's value alone:
the file only changes what it states.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tl_mod_engineering.imports.model import (
    ExistingTag,
    FieldChange,
    ImportPlan,
    ImportRow,
    RowChange,
)


def same_value(old: Any, new: Any) -> bool:
    """Equal values; a number equals the same number written as int or float, a bool is a bool."""
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool) and old == new
    if isinstance(old, int | float) and isinstance(new, int | float):
        return float(old) == float(new)
    return bool(old == new)


def _existing_value(psets: dict[str, Any], pset: str, key: str) -> Any:
    """The value of ``pset.key`` (``key`` may be ``x.name`` for a custom property), or ``None``."""
    node: Any = psets.get(pset)
    for part in key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def row_changes(row: ImportRow, existing: ExistingTag) -> list[FieldChange]:
    """The fields the row states that differ from ``existing``, in a fixed order.

    Order: ``class``, ``service``, then ``psets.<pset>.<property>`` sorted by name. A field the row
    leaves unset (``None``, or a pset property it does not mention) is never a change.
    """
    changes: list[FieldChange] = []
    if row.class_code is not None and row.class_code != existing.class_code:
        changes.append(FieldChange("class", existing.class_code, row.class_code))
    if row.service is not None and row.service != existing.service:
        changes.append(FieldChange("service", existing.service, row.service))
    for pset in sorted(row.psets):
        for key in sorted(row.psets[pset]):
            new = row.psets[pset][key]
            old = _existing_value(existing.psets, pset, key)
            if old is None or not same_value(old, new):
                changes.append(FieldChange(f"psets.{pset}.{key}", old, new))
    return changes


def plan_import(
    rows: Sequence[ImportRow],
    existing: Sequence[ExistingTag],
    *,
    ended: Mapping[str, str] | None = None,
) -> ImportPlan:
    """What importing ``rows`` into a project that holds ``existing`` would do.

    * A row with ``problems`` is ``invalid`` and takes no further part.
    * A second row with a number an earlier row already used is ``invalid`` too: a copy of the row
      with the problem ``duplicate of row <n>`` added (the first one is judged on its own).
    * A valid row whose number an ended tag (``ended``: number to state, ``Superseded`` or
      ``Deleted``) still holds is ``invalid`` too, with the problem ``key '<number>' is already used
      by a <state> tag``: a number is never reused, so apply would refuse it.
    * A valid row whose number no tag has is ``new``.
    * A valid row whose number matches an existing tag is ``changed`` when ``row_changes`` finds
      anything, else its number is ``unchanged``.
    * An existing tag no row of the file mentions, valid or not, is ``removed``.

    Every list keeps file order; ``removed`` is ordered by number.
    """
    by_number = {tag.number: tag for tag in existing}
    plan = ImportPlan()
    first_seen: dict[str, int] = {}
    mentioned: set[str] = set()
    for row in rows:
        if row.number:
            mentioned.add(row.number)
        if row.problems:
            plan.invalid.append(row)
            continue
        if row.number in first_seen:
            plan.invalid.append(
                ImportRow(
                    line=row.line,
                    number=row.number,
                    class_code=row.class_code,
                    service=row.service,
                    psets=row.psets,
                    problems=[f"duplicate of row {first_seen[row.number]}"],
                    raw=row.raw,
                )
            )
            continue
        gone = (ended or {}).get(row.number)
        if gone is not None and row.number not in by_number:
            plan.invalid.append(
                ImportRow(
                    line=row.line,
                    number=row.number,
                    class_code=row.class_code,
                    service=row.service,
                    psets=row.psets,
                    problems=[f"key '{row.number}' is already used by a {gone.lower()} tag"],
                    raw=row.raw,
                )
            )
            continue
        first_seen[row.number] = row.line
        tag = by_number.get(row.number)
        if tag is None:
            plan.new.append(row)
            continue
        changes = row_changes(row, tag)
        if changes:
            plan.changed.append(RowChange(row.line, row.number, tag.id, changes))
        else:
            plan.unchanged.append(row.number)
    plan.removed = sorted(
        (tag for tag in existing if tag.number not in mentioned), key=lambda tag: tag.number
    )
    return plan
