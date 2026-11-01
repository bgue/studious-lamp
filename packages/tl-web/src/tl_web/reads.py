"""``WebReadClient``: the server's own read functions behind the terminal's read method names.

The renderers of the terminal (``labels_load.load_labels``, ``rfi_text``, ``correspondence_text``,
``document_text`` and the ``tl_tui.details`` of the RFI, correspondence and document types) read
through ``tl_tui.client.ClientInterface``. A web page reads through this class instead: every method
calls the **JSON route function** of the API (never a ``tl_core`` query) with the caller's actor and
principal, so a page can show nothing the JSON route would not (spec web-client-i1, sections 5, 6).

* **Viewer.** ``AuthenticationMiddleware`` sets the ADR-0016 viewer for the whole request (a context
  variable). The client is built inside the request and keeps a copy of that context; every read
  runs in it, so a read from another thread still sees the request's viewer, never the default one.
* **Guard.** A route's ``guard(action)`` is a dependency and a direct call skips it; ``_call`` reads
  the action off the route function and asks the same authorizer first, so an admin-only read stays
  admin-only here.
* **Errors.** A route's ``HTTPException`` or domain error passes through. The three terminal reads
  whose contract says "or ``None``" / "``[]``" for a missing or hidden record (``get_record``,
  ``get_record_by_id``, ``history``, ``list_record_files``) answer that way, as ``ApiClient`` does.
* **No other read.** Any other attribute raises ``UnsupportedRead``: a read a page needs and the
  client lacks is a failing check, never a new query.

``MIRRORS`` maps each method to the ``operation_id`` of the route it mirrors (for
``list_code_lists``, the one that reads each list's values; it first reads the list names).
"""

from __future__ import annotations

import contextvars
import functools
from collections.abc import Callable, Sequence
from datetime import date
from typing import TYPE_CHECKING, Any, get_type_hints

from fastapi import Response
from tl_api.context import ApiContext
from tl_api.errors import body_for
from tl_api.routes import actions as actions_routes
from tl_api.routes import admin as admin_routes
from tl_api.routes import correspondence as correspondence_routes
from tl_api.routes import documents as documents_routes
from tl_api.routes import engineering as engineering_routes
from tl_api.routes import files as files_routes
from tl_api.routes import links as links_routes
from tl_api.routes import records as records_routes
from tl_api.routes import reference as reference_routes
from tl_api.routes import threads as threads_routes
from tl_core.auth.types import Principal
from tl_schema.forms import FormMetadata

if TYPE_CHECKING:  # annotations only: tl-web does not declare these packages as dependencies
    from tl_mod_correspondence import reports_technical
    from tl_mod_correspondence import views as correspondence_views
    from tl_mod_correspondence import views_domain as correspondence_domain_views
    from tl_mod_documents import views as document_views

#: Link counts are asked in chunks, as ``ApiClient`` does (the route takes at most 500 ids).
COUNTS_CHUNK = 200

#: method name -> ``operation_id`` of the JSON route it mirrors. A test pins this to the methods.
MIRRORS: dict[str, str] = {
    "list_rfis": "list_rfis",
    "get_rfi": "get_rfi",
    "list_correspondence": "list_correspondence",
    "get_correspondence": "get_correspondence",
    "list_documents": "list_documents",
    "get_document": "get_document",
    "list_clocks": "list_clocks",
    "get_clock": "get_clock",
    "list_correspondence_domains": "list_correspondence_domains",
    "list_code_lists": "list_code_values",
    "list_accounts": "admin_list_accounts",
    "form_metadata": "get_form_metadata",
    "workflow_status": "get_workflow_status",
    "allowed_actions": "get_record_actions",
    "history": "get_record_history",
    "links_of": "get_record_links",
    "link_counts": "get_link_counts",
    "list_record_files": "list_record_files",
    "thread_page": "get_record_thread",
    "get_record": "lookup_record",
    "get_record_by_id": "get_record",
}


class UnsupportedRead(AttributeError):
    """The web client has no such read: a page that needs it is incomplete, not a new query."""

    def __init__(self, name: str) -> None:
        super().__init__(f"WebReadClient has no read named {name!r}")
        self.name = name


@functools.cache
def guard_action(route: Callable[..., Any]) -> str | None:
    """The action of the ``guard(...)`` dependency on a route function's ``actor`` parameter."""
    hint = get_type_hints(route, include_extras=True).get("actor")
    for meta in getattr(hint, "__metadata__", ()):
        action = getattr(getattr(meta, "dependency", None), "action", None)
        if isinstance(action, str):
            return action
    return None


def _missing(exc: BaseException) -> bool:
    """True for the table's ``record_not_found`` (a record that is absent or hidden)."""
    mapped = body_for(exc)
    return mapped is not None and mapped[1].error == "record_not_found"


class WebReadClient:
    """The read methods of ``ClientInterface`` that the web pages and renderers call.

    Build one per request, inside the request (see the module docstring on the viewer).
    """

    def __init__(self, ctx: ApiContext, principal: Principal, *, path: str = "/web") -> None:
        self._ctx = ctx
        self._principal = principal
        self._path = path
        self._request_context = contextvars.copy_context()  # holds the request's viewer

    def __getattr__(self, name: str) -> Any:
        raise UnsupportedRead(name)

    # --- the one door to a route function ------------------------------------------------------

    def _call(self, route: Callable[..., Any], **params: Any) -> Any:
        """``route(ctx=…, actor=…, **params)`` in the request's context, after its guard."""
        action = guard_action(route)

        def run() -> Any:
            if action is not None:
                self._ctx.authorizer.authorize(self._principal, action, self._path)
                self._ctx.authorize(self._principal.actor, action, self._path)
            return route(ctx=self._ctx, actor=self._principal.actor, **params)

        return self._request_context.copy().run(run)

    # --- the RFI log (correspondence module) ---------------------------------------------------

    def list_rfis(
        self,
        project: str,
        *,
        subtype: str | None = None,
        state: str | None = None,
        discipline: str | None = None,
        only_open: bool = False,
        only_overdue: bool = False,
        only_impact: bool = False,
        limit: int = 500,
    ) -> reports_technical.RfiLog:
        found: reports_technical.RfiLog = self._call(
            correspondence_routes.list_rfis,
            project=project,
            subtype=subtype,
            state=state,
            discipline=discipline,
            only_open=only_open,
            only_overdue=only_overdue,
            only_impact=only_impact,
            limit=limit,
        )
        return found

    def get_rfi(self, project: str, number: str) -> correspondence_domain_views.TechnicalView:
        found: correspondence_domain_views.TechnicalView = self._call(
            correspondence_routes.get_rfi, project=project, number=number
        )
        return found

    def list_correspondence(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        domain: str | None = None,
        subtype: str | None = None,
        awaiting_response: bool = False,
        include_void: bool = False,
        sources: bool = True,
        limit: int = 500,
        offset: int = 0,
    ) -> list[correspondence_views.RegisterLineView]:
        found: list[correspondence_views.RegisterLineView] = self._call(
            correspondence_routes.list_correspondence,
            project=project,
            state=state,
            direction=direction,
            domain=domain,
            subtype=subtype,
            awaiting_response=awaiting_response,
            include_void=include_void,
            sources=sources,
            limit=limit,
            offset=offset,
        )
        return found

    def get_correspondence(self, project: str, number: str) -> correspondence_views.ItemView:
        found: correspondence_views.ItemView = self._call(
            correspondence_routes.get_correspondence, project=project, number=number
        )
        return found

    def list_clocks(
        self,
        project: str,
        *,
        open_only: bool = True,
        overdue_only: bool = False,
        due_to: date | None = None,
    ) -> list[correspondence_views.ClockView]:
        found: list[correspondence_views.ClockView] = self._call(
            correspondence_routes.list_clocks,
            project=project,
            open_only=open_only,
            overdue_only=overdue_only,
            due_to=due_to,
        )
        return found

    def get_clock(self, project: str, clock_id: str) -> correspondence_views.ClockView:
        found: correspondence_views.ClockView = self._call(
            correspondence_routes.get_clock, project=project, clock_id=clock_id
        )
        return found

    def list_correspondence_domains(self, project: str) -> list[correspondence_views.DomainView]:
        found: list[correspondence_views.DomainView] = self._call(
            correspondence_routes.list_domains, project=project
        )
        return found

    # --- documents -----------------------------------------------------------------------------

    def list_documents(
        self,
        project: str,
        *,
        doc_type: str | None = None,
        discipline: str | None = None,
        state: str | None = None,
        include_void: bool = False,
        limit: int = 1000,
    ) -> list[document_views.DocumentView]:
        found: list[document_views.DocumentView] = self._call(
            documents_routes.list_documents,
            project=project,
            doc_type=doc_type,
            discipline=discipline,
            state=state,
            include_void=include_void,
            limit=limit,
        )
        return found

    def get_document(self, project: str, number: str) -> document_views.DocumentView:
        found: document_views.DocumentView = self._call(
            documents_routes.get_document, project=project, number=number
        )
        return found

    # --- labels --------------------------------------------------------------------------------

    def list_code_lists(self, scope: str) -> dict[str, dict[str, str]]:
        """``{list name: {code: label}}`` as ``scope`` sees them (usable values only)."""
        project = scope.removeprefix("project:") if scope.startswith("project:") else None
        names = self._call(
            engineering_routes.list_standards, kind="code_list", include_closed=False
        )
        found: dict[str, dict[str, str]] = {}
        for item in names:
            name = str(item.code)
            values = self._call(
                engineering_routes.list_code_values, name=name, project=project, include_all=False
            )
            found[name] = {str(v.code): str(v.label) for v in values}
        return found

    def list_accounts(self) -> Any:
        """Every account: an admin's read; any other principal is refused by the route's guard."""
        return self._call(admin_routes.list_accounts)

    def form_metadata(
        self, scope: str, record_type: str, record_id: str | None = None
    ) -> FormMetadata:
        found: FormMetadata = self._call(
            reference_routes.get_form_metadata,
            scope=scope,
            record_type=record_type,
            record_id=record_id,
        )
        return found

    # --- one record ----------------------------------------------------------------------------

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        """The record with this key in ``scope``, or ``None`` (absent and hidden alike)."""
        try:
            row = self._call(
                records_routes.lookup_record, scope=scope, key=key, response=Response()
            )
        except Exception as exc:
            if _missing(exc):
                return None
            raise
        return dict(row.model_dump())

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        """The record with this id, or ``None`` (absent and hidden alike)."""
        try:
            row = self._call(records_routes.get_record, record_id=record_id, response=Response())
        except Exception as exc:
            if _missing(exc):
                return None
            raise
        return dict(row.model_dump())

    def history(self, record_id: str) -> Any:
        """Every event of the record's stream, oldest first; ``[]`` for a missing or hidden one."""
        try:
            return self._call(records_routes.get_record_history, record_id=record_id)
        except Exception as exc:
            if _missing(exc):
                return []
            raise

    def allowed_actions(self, record_id: str) -> Any:
        """What this principal may do on the record now (``RecordActions``); a hidden record is
        the route's ``record_not_found``."""
        return self._call(
            actions_routes.get_record_actions, principal=self._principal, record_id=record_id
        )

    def workflow_status(self, record_id: str) -> Any:
        return self._call(
            reference_routes.get_workflow_status, principal=self._principal, record_id=record_id
        )

    def links_of(self, record_id: str, *, include_retracted: bool = False) -> Any:
        return self._call(
            links_routes.get_record_links, record_id=record_id, include_retracted=include_retracted
        )

    def link_counts(self, record_ids: Sequence[str]) -> Any:
        ids = list(record_ids)
        counts: dict[str, Any] = {}
        for start in range(0, len(ids), COUNTS_CHUNK):
            counts.update(
                self._call(
                    links_routes.get_link_counts, record_id=ids[start : start + COUNTS_CHUNK]
                )
            )
        return counts

    def list_record_files(self, record_id: str) -> Any:
        """The current files of the record the caller may read; ``[]`` if missing or hidden."""
        row = self.get_record_by_id(record_id)
        if row is None:
            return []
        return self._call(
            files_routes.list_record_files,
            record_id=record_id,
            scope=str(row["scope"]),
            slot=None,
            current_only=True,
        )

    def thread_page(self, record_id: str, *, limit: int = 50, before_seq: int | None = None) -> Any:
        return self._call(
            threads_routes.get_thread, record_id=record_id, limit=limit, before_seq=before_seq
        )
