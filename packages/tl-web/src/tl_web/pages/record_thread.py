"""The Thread tab of the record screen: ``?tab=thread`` on the record page (P2-WEB1-T04).

Read-only: the header line and the messages of the record's thread (``tl_web.present.thread_text``,
the terminal's own text), an ``Older messages`` link when there are more. No composer, no form, no
action. ``?before=<seq>`` asks for the page before that sequence number; anything but an int of at
least 0 means the newest page. A read the service does not offer, or one ``body_for`` maps, shows
its reason in place of the messages; any other exception propagates.
"""

from __future__ import annotations

from typing import Any

from tl_api.errors import body_for

from tl_web import present
from tl_web.pages.record import RecordCtx, Tab, tab


def before_seq(ctx: RecordCtx) -> int | None:
    """``?before=`` as an int of at least 0, or ``None`` (the newest page)."""
    raw = ctx.request.query_params.get("before")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _unavailable(reason: str) -> dict[str, Any]:
    return {"head": "", "lines": "", "empty": f"Thread unavailable: {reason}", "older": ""}


def _thread(ctx: RecordCtx) -> dict[str, Any]:
    try:
        page = ctx.client.thread_page(ctx.record["id"], limit=50, before_seq=before_seq(ctx))
    except NotImplementedError:
        return _unavailable("the thread services are not installed yet")
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        return _unavailable(mapped[1].message)
    lines = present.thread_text.message_lines(page, ctx.labels, technical=ctx.technical)
    if not page.enabled:
        empty = "Threads are not switched on for this type."
    elif not lines:
        empty = "No messages yet."
    else:
        empty = ""
    older = ""
    if page.next_before is not None:
        suffix = "&mode=technical" if ctx.mode_query else ""
        older = f"?tab=thread&before={page.next_before}{suffix}"
    return {
        "head": present.thread_text.header_text(page, ctx.labels, technical=ctx.technical),
        "lines": "\n".join(lines),
        "empty": empty,
        "older": older,
    }


tab(Tab("thread", "Thread", "thread.html", _thread))
