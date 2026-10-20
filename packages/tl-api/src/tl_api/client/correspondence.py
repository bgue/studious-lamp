"""The correspondence module's reads and commands over HTTP (P1-I5).

The same models the embedded services return (``tl_mod_correspondence.views``). A missing item,
thread, party or clock is the module's error (``ItemNotFoundError`` and the others), rebuilt from
the error body; an item the person may not read is the same 404 as one that does not exist.
"""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter
from tl_core.services.commands import Command, CommandResult
from tl_mod_correspondence import views

from tl_api.client.base import ApiClientBase, quote


class CorrespondenceApi(ApiClientBase):
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
    ) -> list[views.RegisterLineView]:
        """The master register (``GET /projects/{project}/correspondence``)."""
        params = {
            "state": state,
            "direction": direction,
            "domain": domain,
            "subtype": subtype,
            "awaiting_response": "true" if awaiting_response else None,
            "include_void": "true" if include_void else None,
            "sources": "false" if not sources else None,
            "limit": limit,
            "offset": offset or None,
        }
        data = self._get_json(f"/projects/{quote(project)}/correspondence", params)
        return self._models(views.RegisterLineView, data)

    def get_correspondence(self, project: str, number: str) -> views.ItemView:
        """One item with its clocks (``GET /projects/{project}/correspondence/{n}``)."""
        data = self._get_json(f"/projects/{quote(project)}/correspondence/{quote(number)}")
        return self._model(views.ItemView, data)

    def get_correspondence_suggestion(self, project: str, number: str) -> views.SuggestionView:
        """The proposal of the suggestion engine for an item."""
        data = self._get_json(
            f"/projects/{quote(project)}/correspondence/{quote(number)}/suggestion"
        )
        return self._model(views.SuggestionView, data)

    def suggest_domain(
        self, project: str, subject: str, body: str | None = None
    ) -> views.SuggestionView:
        """The proposal of the suggestion engine for a text."""
        data = self._get_json(
            f"/projects/{quote(project)}/correspondence-suggestion",
            {"subject": subject, "body": body},
        )
        return self._model(views.SuggestionView, data)

    def list_threads(self, project: str, *, state: str | None = None) -> list[views.ThreadView]:
        data = self._get_json(
            f"/projects/{quote(project)}/correspondence-threads", {"state": state}
        )
        return self._models(views.ThreadView, data)

    def get_thread(self, project: str, number: str) -> views.ThreadView:
        data = self._get_json(f"/projects/{quote(project)}/correspondence-threads/{quote(number)}")
        return self._model(views.ThreadView, data)

    def list_clocks(
        self,
        project: str,
        *,
        open_only: bool = True,
        overdue_only: bool = False,
        due_to: date | None = None,
    ) -> list[views.ClockView]:
        """Response clocks with days left as of the server's today."""
        params = {
            "open_only": None if open_only else "false",
            "overdue_only": "true" if overdue_only else None,
            "due_to": due_to.isoformat() if due_to else None,
        }
        data = self._get_json(f"/projects/{quote(project)}/clocks", params)
        return self._models(views.ClockView, data)

    def get_clock(self, project: str, clock_id: str) -> views.ClockView:
        data = self._get_json(f"/projects/{quote(project)}/clocks/{quote(clock_id)}")
        return self._model(views.ClockView, data)

    def list_parties(
        self, project: str, *, include_inactive: bool = False
    ) -> list[views.PartyView]:
        params = {"include_inactive": "true" if include_inactive else None}
        data = self._get_json(f"/projects/{quote(project)}/parties", params)
        return self._models(views.PartyView, data)

    def get_party(self, project: str, code: str) -> views.PartyView:
        data = self._get_json(f"/projects/{quote(project)}/parties/{quote(code)}")
        return self._model(views.PartyView, data)

    def list_clauses(
        self, project: str, *, include_inactive: bool = False
    ) -> list[views.ClauseView]:
        params = {"include_inactive": "true" if include_inactive else None}
        data = self._get_json(f"/projects/{quote(project)}/clauses", params)
        return self._models(views.ClauseView, data)

    def list_correspondence_domains(self, project: str) -> list[views.DomainView]:
        data = self._get_json(f"/projects/{quote(project)}/correspondence-domains")
        return TypeAdapter(list[views.DomainView]).validate_python(data)

    def correspondence_command(self, name: str, cmd: Command) -> CommandResult:
        """Run any correspondence command by name (``POST /commands/{name}``); the token's actor
        is used. See ``tl_mod_correspondence.commands`` for the names and their access."""
        return self._command(name, cmd)
