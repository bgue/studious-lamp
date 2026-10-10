"""Main area: switches between the grid, an opened record view and the feed pane (brief 10.1)."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import ContentSwitcher

GRID_ID = "grid"
RECORD_ID = "record"
FEED_ID = "feed"


class MainArea(ContentSwitcher):
    """Holds the grid (always mounted, id ``grid``) and at most one record view (id ``record``) or
    feed pane (id ``feed``)."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(initial=GRID_ID, id=id)

    @property
    def showing_record(self) -> bool:
        return self.current == RECORD_ID

    @property
    def showing_feed(self) -> bool:
        return self.current == FEED_ID

    async def show_grid(self) -> None:
        self.current = GRID_ID
        for old in list(self.query(f"#{RECORD_ID}")) + list(self.query(f"#{FEED_ID}")):
            await old.remove()
        self.query_one(f"#{GRID_ID}", Widget).focus()

    async def show_feed(self, view: Widget) -> None:
        """Show the feed pane (replacing an open one); the record view, if any, is closed."""
        for old in list(self.query(f"#{RECORD_ID}")) + list(self.query(f"#{FEED_ID}")):
            await old.remove()
        view.id = FEED_ID
        await self.mount(view)
        self.current = FEED_ID
        view.focus()

    async def show_record(self, view: Widget) -> None:
        for old in list(self.query(f"#{RECORD_ID}")) + list(self.query(f"#{FEED_ID}")):
            await old.remove()
        view.id = RECORD_ID
        await self.mount(view)
        self.current = RECORD_ID
        view.focus()
