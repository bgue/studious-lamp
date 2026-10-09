"""Navigation tree (left panel): company, project, and the views inside it (brief 10.1)."""

from __future__ import annotations

from typing import ClassVar

from textual.widgets import Tree

from tl_tui.messages import NavSelected


class NavTree(Tree[str]):
    """A tree whose leaves carry a view id; choosing one posts `NavSelected(view_id)`."""

    KEY_HINTS: ClassVar[str] = "Enter open view  ↑↓ move  F2 hide  F6 panels"

    def __init__(self, *, company: str, scope: str, id: str | None = None) -> None:  # noqa: A002
        super().__init__(company, data="company", id=id)
        self.company = company
        self.scope = scope

    def on_mount(self) -> None:
        project = self.root.add(self.scope.removeprefix("project:"), data="project", expand=True)
        project.add_leaf("Records", data="records")
        project.add_leaf("★ Saved views (none yet)", data="saved-views")
        self.root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        if event.node.data == "records":
            self.post_message(NavSelected("records"))
