"""Trace tab: the n-hop tree of records reachable through links (brief 7.5, sketch 12).

(P0-I3-T14.) A `Tree` of records: the open record at the root, then the records linked to it, then
theirs, down to a depth the user can change (`+` and `-`). `o` cycles the direction followed
(both, outbound, inbound). Enter on a record opens it as a followed reference. Everything comes from
`ClientInterface.trace`; the tab never touches the services.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode
from tl_core.services.link_trace import TraceNode

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import OpenRecord, StatusMessage
from tl_tui.trace_text import (  # noqa: F401 - the moved names stay importable from here
    DIRECTION_WORDS,
    DIRECTIONS,
    MAX_DEPTH,
    MIN_DEPTH,
    Direction,
    head_text,
    node_text,
    tree_lines,
)

__all__ = [
    "DIRECTIONS",
    "DIRECTION_WORDS",
    "Direction",
    "MAX_DEPTH",
    "MIN_DEPTH",
    "TraceTab",
    "head_text",
    "node_text",
    "tree_lines",
]


class TraceTab(Vertical, can_focus=True):
    """Shows the trace of one record; Enter follows, + and - change the depth, o the direction."""

    KEY_HINTS: ClassVar[str] = "Enter follow  +/- depth  o direction  Esc back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("plus", "depth(1)", show=False),
        Binding("minus", "depth(-1)", show=False),
        Binding("o", "direction", show=False),
    ]

    DEFAULT_CSS = """
    TraceTab { height: auto; }
    TraceTab > Tree { height: auto; max-height: 24; }
    TraceTab > #trace-head { padding: 0 1; }
    """

    def __init__(self, client: ClientInterface, scope: str, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record: dict[str, Any] | None = None
        self.depth = 2
        self.direction: Direction = "both"
        self.lines: list[str] = []  # the tree as plain lines, as last drawn

    def compose(self) -> ComposeResult:
        yield Static(head_text(self.depth, self.direction), id="trace-head", markup=False)
        yield Tree("", id="trace-tree")

    def on_mount(self) -> None:
        # Enter follows a record; it must not also fold or unfold the node.
        self.query_one("#trace-tree", Tree).auto_expand = False

    def on_focus(self) -> None:
        self.query_one("#trace-tree", Tree).focus()

    def show_record(self, record: dict[str, Any]) -> None:
        self.record = record
        self.reload()

    def reload(self) -> None:
        """Read the trace again and redraw. On a client error the display is kept."""
        if self.record is None:
            return
        head = self.query_one("#trace-head", Static)
        try:
            root = self.client.trace(self.record["id"], depth=self.depth, direction=self.direction)
        except NotImplementedError:
            head.update("Trace unavailable: the link services are not installed yet")
            return
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        head.update(head_text(self.depth, self.direction))
        tree: Tree[str] = self.query_one("#trace-tree", Tree)
        tree.clear()
        tree.root.set_label(Text(node_text(root)))
        tree.root.data = root.key
        self._fill(tree.root, root)
        tree.root.expand()
        self.lines = tree_lines(root)

    def _fill(self, parent: TreeNode[str], node: TraceNode) -> None:
        for child in node.children:
            branch = parent.add(Text(node_text(child)), data=child.key, expand=True)
            self._fill(branch, child)

    def action_depth(self, delta: int) -> None:
        depth = max(MIN_DEPTH, min(MAX_DEPTH, self.depth + delta))
        if depth != self.depth:
            self.depth = depth
            self.reload()

    def action_direction(self) -> None:
        index = DIRECTIONS.index(self.direction)
        self.direction = DIRECTIONS[(index + 1) % len(DIRECTIONS)]
        self.reload()

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        event.stop()
        key = event.node.data
        if event.node.is_root or key is None:
            return
        self.post_message(OpenRecord(self.scope, key, follow=True))
