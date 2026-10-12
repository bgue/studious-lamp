"""Comparing a tag list with the tags a project holds (brief 9 M2; P1-I1-T10b).

``plan_import`` is pure: it reads ``ImportRow`` values (``mapping.read_rows``) and ``ExistingTag``
values and returns an ``ImportPlan``. A row that is blank in the file leaves the tag's value alone:
the file only changes what it states.

STUB (P1-I1-T10b): ``same_value``, ``row_changes`` and ``plan_import`` raise NotImplementedError;
the signatures, the docstrings and ``_existing_value`` are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the ``ruff: noqa`` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Sequence
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
    # STEPS
    # 1. If either value is a bool: equal only when both are bools and equal.
    # 2. Else if both are int or float: compare float(old) == float(new).
    # 3. Else old == new, as a bool.
    raise NotImplementedError


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
    # STEPS
    # 1. changes = []. If row.class_code is not None and differs from existing.class_code, append
    #    FieldChange("class", existing.class_code, row.class_code).
    # 2. If row.service is not None and differs from existing.service, append
    #    FieldChange("service", existing.service, row.service).
    # 3. For pset in sorted(row.psets), for key in sorted(row.psets[pset]): new = the row's value,
    #    old = _existing_value(existing.psets, pset, key). If old is None or not
    #    same_value(old, new), append FieldChange(f"psets.{pset}.{key}", old, new).
    # 4. return changes.
    raise NotImplementedError


def plan_import(rows: Sequence[ImportRow], existing: Sequence[ExistingTag]) -> ImportPlan:
    """What importing ``rows`` into a project that holds ``existing`` would do.

    * A row with ``problems`` is ``invalid`` and takes no further part.
    * A second row with a number an earlier row already used is ``invalid`` too: a copy of the row
      with the problem ``duplicate of row <n>`` added (the first one is judged on its own).
    * A valid row whose number no existing tag has is ``new``.
    * A valid row whose number matches an existing tag is ``changed`` when ``row_changes`` finds
      anything, else its number is ``unchanged``.
    * An existing tag no row of the file mentions, valid or not, is ``removed``.

    Every list keeps file order; ``removed`` is ordered by number.
    """
    # STEPS
    # 1. by_number = {tag.number: tag for tag in existing}; plan = ImportPlan();
    #    first_seen: dict[str, int] = {} (number to the row number of its first valid row);
    #    mentioned: set[str] = set() (every non-empty row.number, valid or not).
    # 2. For each row in order: add row.number to mentioned when it is not empty. If row.problems:
    #    append the row to plan.invalid and continue.
    # 3. If row.number is already in first_seen: append to plan.invalid a new ImportRow with the
    #    row's own fields (line, number, class_code, service, psets, raw) and
    #    problems=[f"duplicate of row {first_seen[row.number]}"]; continue.
    # 4. first_seen[row.number] = row.line. tag = by_number.get(row.number). If tag is None, append
    #    the row to plan.new. Else changes = row_changes(row, tag): if there are any, append
    #    RowChange(row.line, row.number, tag.id, changes) to plan.changed, else append row.number
    #    to plan.unchanged.
    # 5. plan.removed = the existing tags whose number is not in mentioned, sorted by number.
    # 6. return plan.
    raise NotImplementedError
