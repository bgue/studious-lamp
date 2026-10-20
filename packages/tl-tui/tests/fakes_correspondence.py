"""In-memory correspondence for `FakeClient` (P1-I5): the correspondence reads of `ClientInterface`.

It holds the views by project and answers the reads the way the embedded client does: items by
number, the void ones only on request, clocks soonest due first with the filters of the real call,
and the module's errors for an unknown number. A command goes to a list the test can read; it
changes nothing. The master register is the lines the test gave it, filtered the way the real one
is. `test_embedded_correspondence.py` compares the reads against the embedded client.
"""

from __future__ import annotations

from datetime import date

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_correspondence import views
from tl_mod_correspondence.commands import API_COMMANDS as CORRESPONDENCE_COMMANDS
from tl_mod_correspondence.errors import (
    ClockNotFoundError,
    ItemNotFoundError,
    PartyNotFoundError,
    ThreadNotFoundError,
)

ENDED_STATES = ("met", "cancelled")


class FakeCorrespondenceSupport:
    """Mixin for `FakeClient`: call `_init_correspondence()` from its `__init__`."""

    def _init_correspondence(self) -> None:
        self._register: dict[str, list[views.RegisterLineView]] = {}
        self._items: dict[str, dict[str, views.ItemView]] = {}
        self._threads: dict[str, dict[str, views.ThreadView]] = {}
        self._clocks: dict[str, dict[str, views.ClockView]] = {}
        self._parties: dict[str, dict[str, views.PartyView]] = {}
        self._clauses: dict[str, list[views.ClauseView]] = {}
        self._domains: dict[str, list[views.DomainView]] = {}
        self._suggestion = views.SuggestionView(
            domain=None, subtype=None, score=0, reasons=[], scores={}
        )
        self.correspondence_commands: list[tuple[str, Command]] = []
        self.is_corr_controller = True  # False: a controller's command raises ForbiddenError

    # --- seeding -----------------------------------------------------------------------------

    def add_correspondence(
        self, project: str, item: views.ItemView, line: views.RegisterLineView | None = None
    ) -> None:
        """Add an item, and its line of the master register."""
        self._items.setdefault(project, {})[item.number] = item
        register = self._register.setdefault(project, [])
        register.append(
            line
            or views.RegisterLineView(
                kind="item", id=item.id, number=item.number, subject=item.subject,
                domain=item.domain, subtype=item.subtype, direction=item.direction,
                state=item.state, on=None, counterparty=None, response_due=None,
                confidentiality="internal",
            )
        )  # fmt: skip

    def add_register_line(self, project: str, line: views.RegisterLineView) -> None:
        self._register.setdefault(project, []).append(line)

    def add_thread(self, project: str, thread: views.ThreadView) -> None:
        self._threads.setdefault(project, {})[thread.number] = thread

    def add_clock(self, project: str, clock: views.ClockView) -> None:
        self._clocks.setdefault(project, {})[clock.id] = clock

    def add_party(self, project: str, party: views.PartyView) -> None:
        self._parties.setdefault(project, {})[party.code] = party

    def add_clause(self, project: str, clause: views.ClauseView) -> None:
        self._clauses.setdefault(project, []).append(clause)

    def add_domain(self, project: str, domain: views.DomainView) -> None:
        self._domains.setdefault(project, []).append(domain)

    def set_suggestion(self, suggestion: views.SuggestionView) -> None:
        self._suggestion = suggestion

    # --- reads -------------------------------------------------------------------------------

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
        self.calls.append("list_correspondence")  # type: ignore[attr-defined]
        lines = [
            line
            for line in self._register.get(project, [])
            if (include_void or line.state != "Void")
            and (sources or line.kind == "item")
            and (state is None or line.state == state)
            and (direction is None or line.direction == direction)
            and (domain is None or line.domain == domain)
            and (subtype is None or line.subtype == subtype)
            and (not awaiting_response or line.response_due is not None)
        ]
        return lines[offset : offset + limit]

    def get_correspondence(self, project: str, number: str) -> views.ItemView:
        self.calls.append("get_correspondence")  # type: ignore[attr-defined]
        found = self._items.get(project, {}).get(number)
        if found is None:
            raise ItemNotFoundError(f"no correspondence item {number!r}")
        return found

    def get_correspondence_suggestion(self, project: str, number: str) -> views.SuggestionView:
        self.calls.append("get_correspondence_suggestion")  # type: ignore[attr-defined]
        self.get_correspondence(project, number)
        return self._suggestion

    def suggest_domain(
        self, project: str, subject: str, body: str | None = None
    ) -> views.SuggestionView:
        self.calls.append("suggest_domain")  # type: ignore[attr-defined]
        return self._suggestion

    def list_threads(self, project: str, *, state: str | None = None) -> list[views.ThreadView]:
        self.calls.append("list_threads")  # type: ignore[attr-defined]
        found = [
            t for t in self._threads.get(project, {}).values() if state is None or t.state == state
        ]
        return sorted(found, key=lambda t: t.last_item_on or "", reverse=True)

    def get_thread(self, project: str, number: str) -> views.ThreadView:
        self.calls.append("get_thread")  # type: ignore[attr-defined]
        found = self._threads.get(project, {}).get(number)
        if found is None:
            raise ThreadNotFoundError(f"no thread {number!r}")
        return found

    def list_clocks(
        self,
        project: str,
        *,
        open_only: bool = True,
        overdue_only: bool = False,
        due_to: date | None = None,
    ) -> list[views.ClockView]:
        self.calls.append("list_clocks")  # type: ignore[attr-defined]
        found = [
            c
            for c in self._clocks.get(project, {}).values()
            if (not open_only or c.state not in ENDED_STATES)
            and (not overdue_only or c.effective_state == "expired")
            and (due_to is None or c.due_on <= due_to.isoformat())
        ]
        return sorted(found, key=lambda c: (c.due_on, c.key))

    def get_clock(self, project: str, clock_id: str) -> views.ClockView:
        self.calls.append("get_clock")  # type: ignore[attr-defined]
        found = self._clocks.get(project, {}).get(clock_id)
        if found is None:
            raise ClockNotFoundError(f"no clock {clock_id!r}")
        return found

    def list_parties(
        self, project: str, *, include_inactive: bool = False
    ) -> list[views.PartyView]:
        self.calls.append("list_parties")  # type: ignore[attr-defined]
        return sorted(
            (p for p in self._parties.get(project, {}).values() if include_inactive or p.is_active),
            key=lambda p: p.code,
        )

    def get_party(self, project: str, code: str) -> views.PartyView:
        self.calls.append("get_party")  # type: ignore[attr-defined]
        found = self._parties.get(project, {}).get(code)
        if found is None:
            raise PartyNotFoundError(f"no party {code!r}")
        return found

    def list_clauses(
        self, project: str, *, include_inactive: bool = False
    ) -> list[views.ClauseView]:
        self.calls.append("list_clauses")  # type: ignore[attr-defined]
        return [c for c in self._clauses.get(project, []) if include_inactive or c.is_active]

    def list_correspondence_domains(self, project: str) -> list[views.DomainView]:
        self.calls.append("list_correspondence_domains")  # type: ignore[attr-defined]
        return list(self._domains.get(project, []))

    def correspondence_command(self, name: str, cmd: Command) -> CommandResult:
        self.calls.append("correspondence_command")  # type: ignore[attr-defined]
        self.correspondence_commands.append((name, cmd))
        if not self.is_corr_controller and name in CONTROLLER_COMMANDS:
            raise ForbiddenError("this action needs the document_controller or admin role")
        return CommandResult(
            stream_id=getattr(cmd, "stream_id", "") or "", key=None, version=1, events=[]
        )


CONTROLLER_COMMANDS = frozenset(
    spec.model.__name__ for spec in CORRESPONDENCE_COMMANDS if spec.access != "user"
)


def seed_correspondence(client: FakeCorrespondenceSupport, project: str = "P123") -> None:
    """Two received items (one with a suggestion), an issued reply with its clock, and a
    transmittal line from the document-control register source."""
    recipients = [views.RecipientView(name="Acme", email="site@acme.test", party_id=None)]

    def item(
        number: str, subject: str, state: str, direction: str, **more: object
    ) -> views.ItemView:
        fields: dict[str, object] = {
            "id": f"ID-{number}", "number": number, "subject": subject, "state": state,
            "direction": direction, "medium": "letter", "received_via": "upload",
            "external_ref": None, "from_name": "Acme Ltd", "from_party_id": None,
            "to": recipients, "cc": [], "sent_on": None, "received_on": "2026-10-19",
            "issued_on": None, "body": None, "confidentiality": "internal", "domain": None,
            "subtype": None, "thread_id": None, "thread_number": None, "responds_to_id": None,
            "responds_to_number": None, "superseded_by_id": None, "response_required": False,
            "response_due": None, "responded_on": None, "triaged_on": None, "triaged_by": None,
            "delivery": "none", "rendition_file_id": None, "version": 1,
        }  # fmt: skip
        return views.ItemView(**{**fields, **more})  # type: ignore[arg-type]

    client.add_correspondence(project, item("P123-COR-0001", "Revised programme", "Received", "in"))
    client.add_correspondence(
        project, item("P123-COR-0002", "Transmittal 12 for review", "Received", "in")
    )
    clock = views.ClockView(
        id="CLK-1", key="P123-COR-0003-C01", item_id="ID-P123-COR-0003",
        item_number="P123-COR-0003", label="Reply expected", kind="response_from_them",
        start_on="2026-10-19", duration_days=14, day_type="calendar", calendar="P123-default@1",
        warn_days=[7, 3, 1], due_on="2026-11-02", state="running", effective_state="running",
        days_left=14, warned_level=None, paused_on=None, closed_on=None, closed_reason=None,
        owner=None, clause_id=None, restarts=0,
    )  # fmt: skip
    client.add_correspondence(
        project,
        item(
            "P123-COR-0003", "Re: Revised programme", "Issued", "out", domain="general",
            subtype="letter", issued_on="2026-10-19", received_on=None, delivery="stub",
            clocks=[clock], thread_number="P123-THR-0001",
        ),
    )  # fmt: skip
    client.add_clock(project, clock)
    client.add_register_line(
        project,
        views.RegisterLineView(
            kind="transmittal", id="TRN-1", number="P123-TRN-0001", subject="Isometrics",
            domain="document_control", subtype="transmittal", direction="out", state="Issued",
            on="2026-10-19", counterparty="Site", response_due=None, confidentiality="internal",
        ),
    )  # fmt: skip
    client.set_suggestion(
        views.SuggestionView(
            domain="general", subtype="letter", score=0,
            reasons=["no keyword matched; the default domain"], scores={"general": 0},
        )
    )  # fmt: skip
