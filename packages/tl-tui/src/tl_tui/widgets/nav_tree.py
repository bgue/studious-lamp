"""Navigation tree (left panel): company, project, and the views inside it (brief 10.1).

STUB (P0-I2-T12b): the public interface is final; the content is replaced by the ticket.
"""

from __future__ import annotations

from textual.widgets import Tree


class NavTree(Tree[str]):
    """A tree whose leaves carry a view id; choosing one posts `NavSelected(view_id)`."""

    def __init__(self, *, company: str, scope: str, id: str | None = None) -> None:  # noqa: A002
        super().__init__(company, data="company", id=id)
        self.company = company
        self.scope = scope

    def on_mount(self) -> None:
        project = self.root.add(self.scope, data="project", expand=True)
        project.add_leaf("Records", data="records")
        self.root.expand()
