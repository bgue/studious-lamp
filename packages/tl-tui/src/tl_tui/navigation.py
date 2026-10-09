"""Back and forward through followed records, like a browser (brief 7.5).

State only. The app calls ``visit`` each time the user opens a record, by following a reference
or from the grid, and ``back`` / ``forward`` for Alt+Left and Alt+Right (which must not call
``visit``).
"""

from __future__ import annotations


class NavHistory:
    """A list of ``(scope, key)`` entries and a position in it."""

    def __init__(self) -> None:
        self._entries: list[tuple[str, str]] = []
        self._index = -1

    @property
    def current(self) -> tuple[str, str] | None:
        return self._entries[self._index] if self._index >= 0 else None

    @property
    def can_back(self) -> bool:
        return self._index > 0

    @property
    def can_forward(self) -> bool:
        return 0 <= self._index < len(self._entries) - 1

    def visit(self, scope: str, key: str) -> None:
        """Note that a record was opened. Forward entries go; the same record again is a no-op."""
        entry = (scope, key)
        if self.current == entry:
            return
        del self._entries[self._index + 1 :]
        self._entries.append(entry)
        self._index = len(self._entries) - 1

    def start(self, scope: str, key: str) -> None:
        """A fresh trail: the user opened a record from a list, not by following a reference."""
        self._entries = [(scope, key)]
        self._index = 0

    def back(self) -> tuple[str, str] | None:
        """Move one entry back and return it, or ``None`` at the start."""
        if not self.can_back:
            return None
        self._index -= 1
        return self._entries[self._index]

    def forward(self) -> tuple[str, str] | None:
        """Move one entry forward and return it, or ``None`` at the end."""
        if not self.can_forward:
            return None
        self._index += 1
        return self._entries[self._index]

    def trail(self, limit: int = 4) -> str:
        """Breadcrumb of the path taken up to the current entry, oldest first: ``A › B › C``.

        Only the last ``limit`` keys are shown, with ``… ›`` in front when earlier ones were cut.
        """
        keys = [key for _scope, key in self._entries[: self._index + 1]]
        if not keys:
            return ""
        shown = keys[-limit:]
        prefix = "… › " if len(keys) > limit else ""
        return prefix + " › ".join(shown)
