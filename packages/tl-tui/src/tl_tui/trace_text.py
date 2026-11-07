"""The Trace tab's text, apart from Textual (P2-WEB1-S6; moved from ``widgets/trace_tab``).

A tree label, the tree as plain lines and the depth and direction line; the terminal's ``TraceTab``
and the web record page both use them. No ``textual`` or ``rich`` here.
"""

from __future__ import annotations

from typing import Literal

from tl_core.services.link_trace import TraceNode

from tl_tui.text import EMPTY

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
    base = f"{node.key or EMPTY}  {node.title}"
    text = f"{node.label}: {base}" if node.label else base
    if node.link_status == "stale":
        text += "  ! stale"
    elif node.link_status == "broken":
        text += "  ✗ broken"
    if node.voided:
        text += "  (voided)"
    if node.more:
        text += f"  +{node.more} more"
    return text


def tree_lines(root: TraceNode) -> list[str]:
    """The tree as plain lines, depth first, children in their given order, two spaces of indent
    per level: ``"  " * node.depth + node_text(node)``."""
    lines = ["  " * root.depth + node_text(root)]
    for child in root.children:
        lines.extend(tree_lines(child))
    return lines


def head_text(depth: int, direction: str) -> str:
    """``Depth 2 · both directions`` (words: both directions, outbound, inbound)."""
    return f"Depth {depth} · {DIRECTION_WORDS[direction]}"
