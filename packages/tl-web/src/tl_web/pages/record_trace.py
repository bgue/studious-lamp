"""The Trace tab of the record page: ``?tab=trace&depth=<n>&dir=<d>`` (P2-WEB1-T03).

Registers itself at import and edits nothing else (``tl_web.pages.record``). The tree lines and
the head line are the terminal's own (``present.trace_text``); the read goes through ``ctx.client``.
Depth and direction are clamped or defaulted here, so a bad query value is never an error.
"""

from __future__ import annotations

from typing import Any

from tl_api.errors import body_for

from tl_web import present
from tl_web.pages.record import RecordCtx, Tab, tab

DEFAULT_DEPTH = 2
DEFAULT_DIRECTION = "both"


def _depth(raw: str) -> int:
    """An integer clamped to the trace's range; anything that is not an integer is the default."""
    try:
        depth = int(raw)
    except ValueError:
        return DEFAULT_DEPTH
    return min(max(depth, present.trace_text.MIN_DEPTH), present.trace_text.MAX_DEPTH)


def _direction(raw: str) -> str:
    return raw if raw in present.trace_text.DIRECTIONS else DEFAULT_DIRECTION


def _url(ctx: RecordCtx, depth: int, direction: str) -> str:
    suffix = "&mode=technical" if ctx.mode_query else ""
    return f"?tab=trace&depth={depth}&dir={direction}{suffix}"


def _controls(ctx: RecordCtx, depth: int, direction: str) -> list[dict[str, Any]]:
    """One control per direction (the chosen one is current), then Less and More for the depth;
    a depth control that would leave the clamp is left out."""
    controls: list[dict[str, Any]] = [
        {
            "label": present.trace_text.DIRECTION_WORDS[d],
            "url": _url(ctx, depth, d),
            "current": d == direction,
        }
        for d in present.trace_text.DIRECTIONS
    ]
    if depth - 1 >= present.trace_text.MIN_DEPTH:
        controls.append({"label": "Less", "url": _url(ctx, depth - 1, direction), "current": False})
    if depth + 1 <= present.trace_text.MAX_DEPTH:
        controls.append({"label": "More", "url": _url(ctx, depth + 1, direction), "current": False})
    return controls


def build(ctx: RecordCtx) -> dict[str, Any]:
    """The head line, the controls and the tree as plain lines (or the line that replaces it)."""
    query = ctx.request.query_params
    depth = _depth(query.get("depth", str(DEFAULT_DEPTH)))
    direction = _direction(query.get("dir", DEFAULT_DIRECTION))
    try:
        root = ctx.client.trace(ctx.record["id"], depth=depth, direction=direction)
        lines = "\n".join(present.trace_text.tree_lines(root))
    except NotImplementedError:
        lines = "Trace unavailable: the link services are not installed yet"
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        lines = f"Trace unavailable: {mapped[1].message}"
    return {
        "head": present.trace_text.head_text(depth, direction),
        "lines": lines,
        "controls": _controls(ctx, depth, direction),
    }


tab(Tab("trace", "Trace", "trace.html", build))
