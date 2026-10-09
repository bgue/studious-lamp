"""The reference tray: a clipboard of records to link later (brief 7.2, sketch 12).

State only, no widgets. The app owns one tray for the session (it is not saved across sessions in
Phase 0). Records are added from the grid, the record view or the Links tab; the tray screen links
the checked ones to the current record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrayItem:
    record_id: str
    key: str
    type: str
    title: str

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> TrayItem:
        """From a record envelope dict (``id``, ``key``, ``type``, ``title``)."""
        return cls(
            record_id=str(record["id"]),
            key=str(record.get("key") or record["id"]),
            type=str(record.get("type") or ""),
            title=str(record.get("title") or ""),
        )


class ReferenceTray:
    """Items in the order they were added; each is checked or not (new items start checked)."""

    def __init__(self) -> None:
        self._items: list[TrayItem] = []
        self._unchecked: set[str] = set()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> list[TrayItem]:
        return list(self._items)

    def contains(self, record_id: str) -> bool:
        return any(item.record_id == record_id for item in self._items)

    def add(self, item: TrayItem) -> bool:
        """Add ``item`` (checked). ``False`` and no change when the record is already there."""
        if self.contains(item.record_id):
            return False
        self._items.append(item)
        return True

    def remove(self, record_id: str) -> None:
        self._items = [i for i in self._items if i.record_id != record_id]
        self._unchecked.discard(record_id)

    def is_checked(self, record_id: str) -> bool:
        return self.contains(record_id) and record_id not in self._unchecked

    def toggle(self, record_id: str) -> None:
        """Flip the check mark; an id not in the tray is ignored."""
        if not self.contains(record_id):
            return
        if record_id in self._unchecked:
            self._unchecked.discard(record_id)
        else:
            self._unchecked.add(record_id)

    def checked_items(self) -> list[TrayItem]:
        return [i for i in self._items if i.record_id not in self._unchecked]

    def clear(self) -> None:
        self._items = []
        self._unchecked = set()
