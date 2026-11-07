"""The Links tab of the record page: ``?tab=links`` (P2-WEB1-T03).

Registers itself at import and edits nothing else (``tl_web.pages.record``). The rows are the
terminal's own (``present.links_text``); the read goes through ``ctx.client`` only. Read-only:
no per-row links, no actions.
"""

from __future__ import annotations

from typing import Any

from tl_api.errors import body_for

from tl_web import present
from tl_web.pages.record import RecordCtx, Tab, tab


def build(ctx: RecordCtx) -> dict[str, Any]:
    """The table headers and rows, or the line that replaces the table (none yet or unavailable)."""
    try:
        views = ctx.client.links_of(ctx.record["id"])
    except NotImplementedError:
        return _empty("Links unavailable: the link services are not installed yet")
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        return _empty(f"Links unavailable: {mapped[1].message}")
    rows = present.links_text.build_rows(views)
    return {
        "headers": list(present.links_text.COLUMNS),
        "rows": [{"group": r.link_id is None, "cells": list(r.cells)} for r in rows],
        "empty": "No links yet." if not rows else "",
    }


def _empty(message: str) -> dict[str, Any]:
    return {"headers": list(present.links_text.COLUMNS), "rows": [], "empty": message}


tab(Tab("links", "Links", "links.html", build))
