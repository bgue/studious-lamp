"""Trace tab: the n-hop tree of records reachable through links (brief 7.5, sketch 12).

(P0-I3-T14.) A `Tree` of records: the open record at the root, then the records linked to it, then
theirs, down to a depth the user can change (`+` and `-`). `o` cycles the direction followed
(both, outbound, inbound). Enter on a record opens it as a followed reference. Everything comes from
`ClientInterface.trace`; the tab never touches the services.

STUB (P0-I3-T14): the layout (`compose`), constructor, attributes and key bindings are final; the
functions and methods marked `raise NotImplementedError` (and the line marked `STUB`) are the
ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode
from tl_core.services.link_trace import TraceNode

from tl_tui.client import ClientInterface

Direction = Literal["both", "out", "in"]
DIRECTIONS: tuple[Direction, ...] = ("both", "out", "in")
DIRECTION_WORDS: dict[str, str] = {"both": "both directions", "out": "outbound", "in": "inbound"}
MIN_DEPTH = 1
MAX_DEPTH = 6


def node_text(node: TraceNode) -> str:
    """One tree label: ``<key>  <title>`` for the root; ``<label>: <key>  <title>`` below it
    (for example ``raised against: NCR-1  Bevel damage``). Then, when they apply, ``  ! stale`` or
    ``  ✗ broken`` for a link in that state, ``  (voided)`` for a voided record, and
    ``  +N more`` when ``node.more`` records are linked but not shown."""
    raise NotImplementedError


def tree_lines(root: TraceNode) -> list[str]:
    """The tree as plain lines, depth first, children in their given order, two spaces of indent
    per level: ``"  " * node.depth + node_text(node)``."""
    raise NotImplementedError


def head_text(depth: int, direction: str) -> str:
    """``Depth 2 · both directions`` (words: both directions, outbound, inbound)."""
    return f"Depth {depth} · {DIRECTION_WORDS[direction]}"


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
        self.record = record  # STUB: the ticket also calls ``self.reload()`` here

    def reload(self) -> None:
        """Read the trace again and redraw. On a client error the display is kept."""
        raise NotImplementedError

    def _fill(self, parent: TreeNode[str], node: TraceNode) -> None:
        raise NotImplementedError

    def action_depth(self, delta: int) -> None:
        raise NotImplementedError

    def action_direction(self) -> None:
        raise NotImplementedError

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        raise NotImplementedError
