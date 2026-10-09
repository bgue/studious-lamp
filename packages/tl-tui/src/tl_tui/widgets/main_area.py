"""Main area: switches between the grid and an opened record view (brief 10.1)."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import ContentSwitcher

GRID_ID = "grid"
RECORD_ID = "record"


class MainArea(ContentSwitcher):
    """Holds the grid (always mounted, id ``grid``) and at most one record view (id ``record``)."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(initial=GRID_ID, id=id)

    @property
    def showing_record(self) -> bool:
        return self.current == RECORD_ID

    async def show_grid(self) -> None:
        self.current = GRID_ID
        for old in list(self.query(f"#{RECORD_ID}")):
            await old.remove()
        self.query_one(f"#{GRID_ID}", Widget).focus()

    async def show_record(self, view: Widget) -> None:
        for old in list(self.query(f"#{RECORD_ID}")):
            await old.remove()
        view.id = RECORD_ID
        await self.mount(view)
        self.current = RECORD_ID
        view.focus()
