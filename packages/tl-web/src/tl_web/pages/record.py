"""The record screen on the web: ``GET /web/p/{project}/records/{record_id}`` (P2-WEB1-S6).

The page of the terminal's record view: heading ``number · subject``, the state line with badges,
the actions bar and the tabs. The text of each part is the terminal's own (``tl_web.present``:
``record_text``, ``properties_text``, ...), so the two screens share one implementation.

A record that is missing, hidden, in another project, or asked for with a tab that is unknown or
not visible, is the one 404 page, before any tab reads anything (ADR-0016: hidden is missing).

Tabs are a registry. This module registers Details, Properties and History; every other tab is a
module listed in ``TAB_MODULES`` that calls ``tab(Tab(...))`` at import and edits nothing else.

Recipe for a tab module (here the Links tab; ``record_links.py``)::

    from tl_web.pages.record import RecordCtx, Tab, tab

    def build(ctx: RecordCtx) -> dict[str, Any]:
        views = ctx.client.links_of(ctx.record["id"])      # reads go through ctx.client
        rows = present.links_text.build_rows(views)
        return {"rows": [r.cells for r in rows]}           # the names the template uses

    tab(Tab("links", "Links", "links.html", build))        # template: templates/record/links.html

``build`` receives a ``RecordCtx`` and returns the values its template uses. They must not reuse a
name of the frame (``FRAME_NAMES``). Links to other pages carry ``ctx.mode_query``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Any
from urllib.parse import quote

from fastapi import Request, Response
from tl_api.auth import PRINCIPAL_KEY
from tl_api.errors import body_for
from tl_core.auth.types import Principal

from tl_web import present
from tl_web.app import PROJECT_ID, render
from tl_web.log import TECHNICAL, action_views, offered_actions
from tl_web.reads import WebReadClient
from tl_web.webroute import not_found_page, web_router

router = web_router()

#: The tabs in display order; a registered tab not named here follows them, in registration order.
ORDER = ("details", "properties", "links", "history", "trace", "thread", "files")
#: Modules that register more tabs; loaded on the first request, skipped while they do not exist.
TAB_MODULES = (
    "tl_web.pages.record_links",
    "tl_web.pages.record_trace",
    "tl_web.pages.record_thread",
    "tl_web.pages.record_files",
)
#: The names the frame passes to its template; a tab's ``build`` may not return one of them.
FRAME_NAMES = frozenset(
    {
        "project",
        "record",
        "header",
        "nav",
        "actions",
        "open_url",
        "notice",
        "text",
        "tab_name",
        "tab_template",
        "csrf",
    }
)


@dataclass(frozen=True)
class RecordCtx:
    """What a tab sees: the request, the project, the record row, the project's labels, the display
    mode, the read client (the only door to data) and ``mode_query`` (``?mode=technical`` or ``""``,
    to put on every link)."""

    request: Request
    project: str
    record: dict[str, Any]
    labels: present.Labels
    technical: bool
    client: WebReadClient
    mode_query: str


@dataclass(frozen=True)
class Tab:
    """One tab: ``name`` is the ``?tab=`` value, ``template`` a file of ``templates/record/``,
    ``build`` returns the values the template uses, ``visible`` hides the tab (a hidden tab is a
    404, as an unknown one)."""

    name: str
    label: str
    template: str
    build: Callable[[RecordCtx], dict[str, Any]]
    visible: Callable[[RecordCtx], bool] = lambda _: True  # noqa: E731


TABS: dict[str, Tab] = {}


def tab(t: Tab) -> None:
    """Register a tab; a second tab of the same name is refused."""
    if t.name in TABS:
        raise ValueError(f"record tab {t.name!r} is already registered")
    TABS[t.name] = t


_loaded = False


def _exists(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except ModuleNotFoundError:  # the parent package is not there yet
        return False


def load_tab_modules() -> None:
    """Import the modules of ``TAB_MODULES`` that exist, once (on the first request)."""
    global _loaded  # noqa: PLW0603
    if _loaded:
        return
    _loaded = True
    for name in TAB_MODULES:
        if _exists(name):
            import_module(name)


def _ordered() -> list[Tab]:
    known = [TABS[n] for n in ORDER if n in TABS]
    return known + [t for n, t in TABS.items() if n not in ORDER]


# --- the three tabs of this piece -------------------------------------------------------------


def mode_for(technical: bool) -> present.display.DisplayMode:
    """A ``DisplayMode`` whose ``technical`` is the page's (the class takes no argument)."""
    mode = present.display.DisplayMode()
    mode.technical = technical
    return mode


def _details(ctx: RecordCtx) -> dict[str, Any]:
    rows = present.details.details_for(
        present.as_client(ctx.client),
        ctx.project,
        ctx.record,
        ctx.labels,
        mode_for(ctx.technical),
    )
    return {"lines": present.record_text.details_lines(rows)}


def _properties(ctx: RecordCtx) -> dict[str, Any]:
    record = ctx.record
    try:
        meta = ctx.client.form_metadata(f"project:{ctx.project}", record["type"], record["id"])
        report = ctx.client.conformance(record["id"])
    except NotImplementedError:
        return {"lines": "Properties unavailable: the property services are not installed yet"}
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        return {"lines": f"Properties unavailable: {mapped[1].message}"}
    return {
        "lines": present.properties_text.psets_text(meta, record, report, technical=ctx.technical)
    }


def _history(ctx: RecordCtx) -> dict[str, Any]:
    events = ctx.client.history(ctx.record["id"])
    return {
        "headers": present.record_text.history_columns(ctx.technical),
        "rows": [
            present.record_text.history_cells(event, ctx.labels, technical=ctx.technical)
            for event in reversed(events)
        ],
    }


tab(Tab("details", "Details", "details.html", _details))
tab(Tab("properties", "Properties", "properties.html", _properties))
tab(Tab("history", "History", "history.html", _history))


# --- the page ---------------------------------------------------------------------------------


def _badges(client: WebReadClient, record_id: str) -> str:
    """``since <time>`` and the link counts; a read that fails leaves its part out."""
    entered: str | None = None
    try:
        entered = client.workflow_status(record_id).entered_at
    except Exception as exc:
        if body_for(exc) is None and not isinstance(exc, NotImplementedError):
            raise
    counts = None
    try:
        counts = client.link_counts([record_id]).get(record_id)
    except Exception as exc:
        if body_for(exc) is None and not isinstance(exc, NotImplementedError):
            raise
    return present.record_text.badges_text(entered, counts)


@router.get("/p/{project}/records/{record_id}")
def record_page(
    request: Request, project: str, record_id: str, tab: str = "details", mode: str = ""
) -> Response:
    """The record: header, tabs, actions bar and the active tab. Anything missing, hidden, of
    another project, or a tab that is unknown or not visible, is the one 404 page."""
    load_tab_modules()
    chosen = TABS.get(tab)
    if chosen is None or not PROJECT_ID.fullmatch(project):
        return not_found_page(request)
    principal: Principal = request.scope[PRINCIPAL_KEY]
    client = WebReadClient(request.app.state.ctx, principal, path=request.url.path)
    record = client.get_record_by_id(record_id)
    if record is None or record["scope"] != f"project:{project}":
        return not_found_page(request)
    wants = mode == TECHNICAL
    technical = wants and principal.is_admin
    scope = f"project:{project}"
    ctx = RecordCtx(
        request=request,
        project=project,
        record=record,
        labels=present.load_labels(
            present.as_client(client), scope, ("core.Record", str(record["type"]))
        ),
        technical=technical,
        client=client,
        mode_query=f"?mode={TECHNICAL}" if technical else "",
    )
    shown = [t for t in _ordered() if t.visible(ctx)]
    if chosen not in shown:
        return not_found_page(request)
    values = chosen.build(ctx)
    clash = FRAME_NAMES & values.keys()
    if clash:
        raise ValueError(f"record tab {chosen.name!r} returns reserved names {sorted(clash)}")
    suffix = f"&mode={TECHNICAL}" if technical else ""
    parts = present.record_text.header_parts(
        record, _badges(client, record["id"]), technical=technical
    )
    template = (
        chosen.template if chosen.template.startswith("record/") else f"record/{chosen.template}"
    )
    return render(
        request,
        "record/frame.html",
        project=project,
        record=record,
        header={
            "identity": parts.identity,
            "state": f"{parts.status}{parts.version} · {parts.mark}{parts.rest}",
        },
        nav=[
            {
                "label": t.label,
                "url": f"?tab={quote(t.name, safe='')}{suffix}",
                "current": t is chosen,
            }
            for t in shown
        ],
        actions=action_views(
            project, record["id"], offered_actions(client.allowed_actions(record["id"]))
        ),
        open_url="",
        notice=present.REFUSAL if wants and not technical else "",
        tab_name=chosen.name,
        tab_template=template,
        **values,
    )
