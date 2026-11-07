"""``WebLog``: the log standard on the web (spec web-client-i1, section 7).

A web log is the terminal's ``LogScreen`` with the same hooks and one template. A page module
subclasses ``WebLog`` (``LOG_NAME``, ``KEY_HINTS``, ``columns``, ``load_rows``, ``row_key``,
``row_cells``, ``row_record``, ``panel_page`` (or ``panel_text``), ``summary_text``;
``actions_for`` is usually the default), calls ``register(slug, cls)`` and adds its own
``GET /web/p/{project}/{slug}`` that answers
``MyLog.page(request, project, q=q, sel=sel, mode=mode)``. This module owns the htmx partial
``GET /web/p/{project}/{log}/panel/{number:path}``.

Recipe for a log page (copy it, change the hooks)::

    router = web_router()

    class RfiWebLog(WebLog[RfiLogLine]):
        LOG_NAME = "RFI log"
        LABEL_TYPES = ("correspondence.TechnicalItem",)
        def columns(self): return present.rfi_text.RFI_COLUMNS
        def drop_order(self): return present.rfi_text.RFI_DROP
        def load_rows(self): ...        # self.client.list_rfis(...) and set the summary
        def row_key(self, row): return row.id
        def row_record(self, row): return (row.number, row.subject)
        def row_cells(self, row):
            return present.rfi_text.rfi_cells(row, self.labels, technical=self.technical)
        def panel_text(self, row): ...  # present.plain_lines(rfi_page(...))
        def summary_text(self): return self._summary

    register("rfis", RfiWebLog)

    @router.get("/p/{project}/rfis")
    def rfi_log(request: Request, project: str, q: str = "", sel: str = "",
                mode: str = "") -> Response:
        return RfiWebLog.page(request, project, q=q, sel=sel, mode=mode)

``WebAction`` mirrors ``tl_tui.widgets.log_actions.LogAction``: ``key`` and ``label`` are the same,
and ``command`` (the name of the command to run) takes the place of the callable ``run``: the
command is run by the POST route of ``tl_web.actions``, which checks it is offered right then.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Self
from urllib.parse import quote

from fastapi import Request, Response
from tl_api.auth import PRINCIPAL_KEY
from tl_core.auth.types import Principal

from tl_web import present
from tl_web.app import PROJECT_ID, render
from tl_web.reads import WebReadClient
from tl_web.webroute import not_found_page, web_router

router = web_router()

_SLUG = re.compile(r"[a-z][a-z0-9-]{0,31}")
TECHNICAL = "technical"


@dataclass(frozen=True)
class WebAction:
    """One thing a person may do to the selected record, as the server offers it now.

    Mirrors ``LogAction`` of the terminal (``key``, ``label``); ``command`` is the command name the
    POST route runs, and ``asks`` says the action opens a form (questions or a confirmation) first.
    """

    key: str
    label: str
    command: str
    asks: bool = False


def offered_actions(offers: Any, own_keys: frozenset[str] = frozenset()) -> list[WebAction]:
    """One ``WebAction`` per offer that has an ``ACTION_UI`` entry, in the order the server gave.

    Like ``log_actions`` and ``usable_actions`` of the terminal: an offer without an entry is left
    out, a key the log binds itself (``own_keys``) is not offered, and of two offers that share a
    key (``VoidDraft`` and ``VoidCorrespondence``) the first wins.
    """
    ui = present.without_keys(present.ACTION_UI, own_keys)
    seen: set[str] = set()
    found: list[WebAction] = []
    for offer in offers.actions:
        entry = ui.get(offer.command)
        if entry is None or entry.key in seen:
            continue
        seen.add(entry.key)
        found.append(
            WebAction(
                entry.key,
                offer.label,
                offer.command,
                asks=bool(entry.fields) or entry.confirm is not None,
            )
        )
    return found


def action_views(
    project: str, record_id: str, actions: Sequence[WebAction]
) -> list[dict[str, Any]]:
    """The actions bar's buttons for ``actions.html``: key, label, command and the URLs of the POST
    route (``tl_web.actions``) that runs it and of its question form."""
    base = f"/web/p/{project}/records/{quote(record_id, safe='')}/do"
    return [
        {
            "key": a.key,
            "key_label": present.key_label(a.key),
            "label": a.label,
            "command": a.command,
            "asks": a.asks,
            "url": f"{base}/{a.command}",
            "form_url": f"{base}/{a.command}/form",
        }
        for a in actions
    ]


class WebLog[Row]:
    """The base of every web log. One instance serves one request."""

    SLUG: ClassVar[str] = ""  # set by ``register``; the page is ``/web/p/{project}/{SLUG}``
    LOG_NAME: ClassVar[str] = "Log"
    KEY_HINTS: ClassVar[str] = "Up/Down move  Enter open  / filter  F5 reload  Esc back"
    LABEL_TYPES: ClassVar[tuple[str, ...]] = ("core.Record",)  # types whose code lists are wanted
    OWN_KEYS: ClassVar[frozenset[str]] = frozenset()  # action keys the log binds itself

    def __init__(self, request: Request, project: str, *, technical: bool = False) -> None:
        self.request = request
        self.project = project
        self.technical = technical
        self.principal: Principal = request.scope[PRINCIPAL_KEY]
        self.client = WebReadClient(request.app.state.ctx, self.principal, path=request.url.path)
        self._labels: present.Labels | None = None

    # --- the log's hooks (the same names as LogScreen) ------------------------------------------

    @property
    def labels(self) -> present.Labels:
        """The labels of the project, read once per request."""
        if self._labels is None:
            self._labels = present.load_labels(
                present.as_client(self.client), f"project:{self.project}", self.LABEL_TYPES
            )
        return self._labels

    def columns(self) -> Sequence[str]:
        raise NotImplementedError

    def load_rows(self) -> Sequence[Row]:
        """Read the rows (and work out the summary line)."""
        raise NotImplementedError

    def row_key(self, row: Row) -> str:
        """The record id of the row."""
        raise NotImplementedError

    def row_open_key(self, row: Row) -> str | None:
        """The record id the Open link goes to; ``None`` for a row with no record page (no link)."""
        return self.row_key(row)

    def row_cells(self, row: Row) -> Sequence[str]:
        """Plain text per column, never raw codes (``self.technical``: an admin asked for them)."""
        raise NotImplementedError

    def row_record(self, row: Row) -> tuple[str, str]:
        """``(number, title)`` of the record, for the breadcrumb and the panel URL."""
        raise NotImplementedError

    def panel_page(self, row: Row) -> present.Page | None:
        """The panel of ``row`` as a layout ``Page`` (rendered as HTML), or ``None`` for a log
        whose panel is free text (it then implements ``panel_text``)."""
        return None

    def panel_text(self, row: Row | None) -> list[str]:
        """The panel of ``row`` as the terminal's plain lines; by default the plain lines of
        ``panel_page``."""
        page = self.panel_page(row) if row is not None else None
        if page is None:
            raise NotImplementedError
        return present.plain_lines(page)

    def panel_image(self, row: Row) -> str:
        """The URL of a picture for the top of the panel (a page-1 preview), or ``""`` for none.
        The URL must be same-origin (``img-src 'self'``) and carry the scope it needs."""
        return ""

    def keep_columns(self) -> Sequence[str]:
        """The columns that always show: the first, the State and the subject. Any other column
        whose value is the same in every shown row (two or more) is dropped."""
        names = list(self.columns())
        flex = present.log_text.flex_index(names)
        return [*names[:1], "State", *([names[flex]] if flex is not None else [])]

    def drop_order(self) -> Sequence[str]:
        """The columns a narrow screen leaves out, least needed first (hidden by CSS width)."""
        return []

    def actions_for(self, row: Row) -> Sequence[WebAction]:
        """What the viewer may do to ``row`` now: the server's ``allowed_actions``, as ``ACTION_UI``
        presents them."""
        return offered_actions(self.client.allowed_actions(self.row_key(row)), self.OWN_KEYS)

    def summary_text(self) -> str:
        """The count or summary line; ``""`` when the log has none."""
        return ""

    # --- request plumbing -------------------------------------------------------------------------

    @classmethod
    def for_request(cls, request: Request, project: str, mode: str) -> tuple[Self, str | None]:
        """The log for this request and the notice to show: ``?mode=technical`` is for an admin
        only; anyone else gets plain and ``Technical details are for admins``. Never stored."""
        principal: Principal = request.scope[PRINCIPAL_KEY]
        wants = mode == TECHNICAL
        technical = wants and principal.is_admin
        return cls(request, project, technical=technical), (
            present.REFUSAL if wants and not technical else None
        )

    def row_for(self, number: str) -> Row | None:
        """The row whose record has this number (a hidden or unknown number is not among them)."""
        return next((r for r in self.load_rows() if self.row_record(r)[0] == number), None)

    def _mode_query(self) -> str:
        return f"?mode={TECHNICAL}" if self.technical else ""

    def page_url(self) -> str:
        return f"/web/p/{self.project}/{self.SLUG}"

    def _panel_url(self, number: str) -> str:
        quoted = quote(number, safe="/")
        return f"{self.page_url()}/panel/{quoted}{self._mode_query()}"

    def _action_views(self, record_id: str, actions: Sequence[WebAction]) -> list[dict[str, Any]]:
        return action_views(self.project, record_id, actions)

    def _open_url(self, row: Row) -> str:
        key = self.row_open_key(row)
        if key is None:
            return ""
        return f"/web/p/{self.project}/records/{quote(key, safe='')}{self._mode_query()}"

    def _selected_context(self, row: Row | None) -> dict[str, Any]:
        number, title = self.row_record(row) if row is not None else ("", "")
        crumb = present.breadcrumb_text(
            self.project, self.LOG_NAME, number or None, title or None, 1000
        )
        actions = self.actions_for(row) if row is not None else []
        page = self.panel_page(row) if row is not None else None
        if row is None:
            lines = ["Nothing here."]
        elif page is None:
            lines = self.panel_text(row)
        else:
            lines = present.plain_lines(page)
        return {
            "crumb": crumb,
            "panel": lines,
            "panel_page": page,
            "tone": present.tone,
            "state_tone": present.state_tone,
            "page_blocks": present.page_blocks,
            "panel_image": self.panel_image(row) if row is not None else "",
            "actions": self._action_views(self.row_key(row), actions) if row is not None else [],
            "open_url": self._open_url(row) if row is not None else "",
        }

    # --- the two answers ----------------------------------------------------------------------

    @classmethod
    def page(
        cls, request: Request, project: str, *, q: str = "", sel: str = "", mode: str = ""
    ) -> Response:
        """The whole log page: the seven regions, the row ``sel`` (else the first) selected."""
        if not PROJECT_ID.fullmatch(project):
            return not_found_page(request)
        log, notice = cls.for_request(request, project, mode)
        return log._render_page(q, sel, notice)

    def _render_page(self, q: str, sel: str, notice: str | None) -> Response:
        rows = list(self.load_rows())
        summary = self.summary_text()
        needle = q.strip().lower()
        cells = [tuple(self.row_cells(r)) for r in rows]
        kept = [
            (r, c)
            for r, c in zip(rows, cells, strict=True)
            if not needle or needle in " ".join(c).lower()
        ]
        names = list(self.columns())
        shown = present.visible_columns(names, [c for _, c in kept], self.keep_columns())
        flex = present.log_text.flex_index(names)
        drop = set(self.drop_order())
        selected = next((r for r, _ in kept if self.row_record(r)[0] == sel), None)
        if selected is None and kept:
            selected = kept[0][0]
        columns = [
            {"name": names[i], "cls": _column_class(names[i], flex == i, names[i] in drop)}
            for i in shown
        ]
        table_rows = [
            {
                "number": self.row_record(r)[0],
                "selected": r is selected,
                "cells": [
                    {"text": c[i], "cls": columns[n]["cls"], "badge": _badge(names[i], c[i])}
                    for n, i in enumerate(shown)
                ],
                "panel_url": self._panel_url(self.row_record(r)[0]),
                "open_url": self._open_url(r),
            }
            for r, c in kept
        ]
        return render(
            self.request,
            "log.html",
            project=self.project,
            log_name=self.LOG_NAME,
            page_url=self.page_url(),
            mode=TECHNICAL if self.technical else "",
            q=q,
            columns=columns,
            rows=table_rows,
            key_hints=self.KEY_HINTS,
            text=notice or present.web_summary(summary),
            **self._selected_context(selected),
        )

    def panel_response(self, number: str, notice: str | None) -> Response:
        """The htmx partial: the panel of one row, with the actions bar, the breadcrumb and the
        status line out of band. A hidden or unknown number is the one 404 page."""
        row = self.row_for(number)
        if row is None:
            return not_found_page(self.request)
        summary = self.summary_text()
        return render(
            self.request,
            "panel.html",
            text=notice or present.web_summary(summary),
            oob=True,
            **self._selected_context(row),
        )


def _badge(column: str, text: str) -> str:
    """The tone of a State cell (``done``, ``waiting``, ``bad``, ``neutral``); ``""`` for any other
    cell or an empty one."""
    if column != "State" or not text.strip():
        return ""
    return present.state_tone(text)


def _column_class(name: str, flex: bool, drop: bool) -> str:
    words = ["tl-flex"] if flex else []
    if drop:
        words.append("tl-drop")
    if name == "State":
        words.append("tl-state")
    return " ".join(words)


#: The logs by slug, filled by ``register`` when a page module is imported.
LOGS: dict[str, type[WebLog[Any]]] = {}


def register(slug: str, cls: type[WebLog[Any]]) -> None:
    """Make ``cls`` the log called ``slug``: it sets ``cls.SLUG`` and answers the panel route."""
    if not _SLUG.fullmatch(slug):
        raise ValueError(f"log slug {slug!r} is not a lower-case word")
    known = LOGS.get(slug)
    if known is not None and known is not cls:
        raise ValueError(f"log slug {slug!r} is already registered")
    cls.SLUG = slug
    LOGS[slug] = cls


@router.get("/p/{project}/{log}/panel/{number:path}")
def panel(request: Request, project: str, log: str, number: str, mode: str = "") -> Response:
    """The panel, actions bar and status line of one row (htmx). A slug that is not registered, a
    hidden number and an unknown number all answer the same 404 page."""
    cls = LOGS.get(log)
    if cls is None or not PROJECT_ID.fullmatch(project):
        return not_found_page(request)
    instance, notice = cls.for_request(request, project, mode)
    return instance.panel_response(number, notice)
