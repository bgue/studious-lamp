"""The difference between two derived tables, by key column (brief 9 M1: a new derived revision
carries a diff against the prior derived data).

Pure: two tables of text cells in, a ``DerivedDiff`` out. Rows are matched by the value of the key
column (trimmed); a cell is compared as trimmed text, and an empty cell equals a missing one. A
key that appears twice in one table is judged by its first row and listed in ``duplicate_keys``; a
row with an empty key is counted in ``blank_key_rows`` and takes no part. The lists are capped at
``MAX_LISTED`` entries each, the counts are exact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel
from tl_core.derivation.types import Cell

MAX_LISTED = 1000


class FieldChange(BaseModel):
    column: str
    old: str | None
    new: str | None


class RowChange(BaseModel):
    key: str
    fields: list[FieldChange]


class DerivedDiff(BaseModel):
    key_column: str
    added: list[str]
    removed: list[str]
    changed: list[RowChange]
    added_count: int
    removed_count: int
    changed_count: int
    unchanged_count: int
    columns_added: list[str]
    columns_removed: list[str]
    duplicate_keys: list[str]
    blank_key_rows: int
    #: True when a list above was cut at ``MAX_LISTED``.
    truncated: bool


def _norm(cell: Cell) -> str | None:
    if cell is None:
        return None
    text = cell.strip()
    return text or None


def _index(
    rows: Sequence[Mapping[str, Cell]], key_column: str, duplicates: list[str]
) -> tuple[dict[str, Mapping[str, Cell]], int]:
    found: dict[str, Mapping[str, Cell]] = {}
    blank = 0
    for row in rows:
        key = _norm(row.get(key_column))
        if key is None:
            blank += 1
        elif key in found:
            if key not in duplicates:
                duplicates.append(key)
        else:
            found[key] = row
    return found, blank


def diff_rows(
    old_columns: Sequence[str],
    old_rows: Sequence[Mapping[str, Cell]],
    new_columns: Sequence[str],
    new_rows: Sequence[Mapping[str, Cell]],
    key_column: str,
) -> DerivedDiff:
    """What changed from the old table to the new one.

    ``added`` and ``changed`` are in the order of the new table, ``removed`` in the order of the
    old one. A changed row lists, in the new table's column order, each column of either table
    whose normalised value differs. ``columns_added`` and ``columns_removed`` follow the column
    order of the table that has them.
    """
    duplicates: list[str] = []
    old_index, old_blank = _index(old_rows, key_column, duplicates)
    new_index, new_blank = _index(new_rows, key_column, duplicates)
    columns = [*new_columns, *(c for c in old_columns if c not in new_columns)]
    added: list[str] = []
    changed: list[RowChange] = []
    unchanged = 0
    for key, row in new_index.items():
        before = old_index.get(key)
        if before is None:
            added.append(key)
            continue
        fields = [
            FieldChange(column=c, old=_norm(before.get(c)), new=_norm(row.get(c)))
            for c in columns
            if _norm(before.get(c)) != _norm(row.get(c))
        ]
        if fields:
            changed.append(RowChange(key=key, fields=fields))
        else:
            unchanged += 1
    removed = [key for key in old_index if key not in new_index]
    return DerivedDiff(
        key_column=key_column,
        added=added[:MAX_LISTED],
        removed=removed[:MAX_LISTED],
        changed=changed[:MAX_LISTED],
        added_count=len(added),
        removed_count=len(removed),
        changed_count=len(changed),
        unchanged_count=unchanged,
        columns_added=[c for c in new_columns if c not in old_columns],
        columns_removed=[c for c in old_columns if c not in new_columns],
        duplicate_keys=duplicates[:MAX_LISTED],
        blank_key_rows=old_blank + new_blank,
        truncated=max(len(added), len(removed), len(changed), len(duplicates)) > MAX_LISTED,
    )
