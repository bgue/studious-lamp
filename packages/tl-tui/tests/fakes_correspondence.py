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
from tl_mod_correspondence import (
    evidence,
    reports_commercial,
    reports_technical,
    views,
    views_domain,
)
from tl_mod_correspondence.commands import API_COMMANDS as CORRESPONDENCE_COMMANDS
from tl_mod_correspondence.errors import (
    ClockNotFoundError,
    EvidenceDateError,
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
        self._rfi_lines: dict[str, list[reports_technical.RfiLogLine]] = {}
        self._rfis: dict[str, dict[str, views_domain.TechnicalView]] = {}
        self._commercial_lines: dict[str, list[reports_commercial.CommercialLine]] = {}
        self._commercial: dict[str, dict[str, views_domain.CommercialView]] = {}
        self._trails: dict[str, dict[str, evidence.EvidenceTrail]] = {}
        self.trail_requests: list[tuple[str, date | None]] = []  # (number, as_of) asked for
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

    def add_rfi(
        self,
        project: str,
        view: views_domain.TechnicalView,
        line: reports_technical.RfiLogLine,
    ) -> None:
        """Add an RFI (its view) and its line of the RFI log."""
        self._rfis.setdefault(project, {})[view.number] = view
        self._rfi_lines.setdefault(project, []).append(line)

    def add_commercial(
        self,
        project: str,
        view: views_domain.CommercialView,
        line: reports_commercial.CommercialLine,
    ) -> None:
        """Add a Commercial item (its view) and its line of the register."""
        self._commercial.setdefault(project, {})[view.number] = view
        self._commercial_lines.setdefault(project, []).append(line)

    def add_trail(self, project: str, trail: evidence.EvidenceTrail, number: str) -> None:
        """The evidence trail the fake answers for ``number`` (whatever day is asked)."""
        self._trails.setdefault(project, {})[number] = trail

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
        self.calls.append("list_rfis")  # type: ignore[attr-defined]
        every = self._rfi_lines.get(project, [])
        lines = [
            line
            for line in every
            if (subtype is None or line.subtype == subtype)
            and (state is None or line.state == state)
            and (discipline is None or line.discipline == discipline)
            and (not only_open or line.state not in ("Answered", "Accepted", "Closed", "Void"))
            and (not only_overdue or line.overdue)
            and (not only_impact or "yes" in (line.cost_impact, line.schedule_impact))
        ]
        return reports_technical.RfiLog(
            scope=project,
            as_of="2026-10-20",
            lines=lines[:limit],
            total=len(lines),
            answered=sum(1 for line in lines if line.answered_on),
            open=sum(1 for line in lines if line.state not in ("Closed", "Void")),
            overdue=sum(1 for line in lines if line.overdue),
            impact_yes=sum(
                1 for line in lines if "yes" in (line.cost_impact, line.schedule_impact)
            ),
            average_response_days=None,
        )

    def get_rfi(self, project: str, number: str) -> views_domain.TechnicalView:
        self.calls.append("get_rfi")  # type: ignore[attr-defined]
        found = self._rfis.get(project, {}).get(number)
        if found is None:
            raise ItemNotFoundError(f"no technical item {number!r} in scope {project!r}")
        return found

    def list_commercial(
        self,
        project: str,
        *,
        subtype: str | None = None,
        state: str | None = None,
        only_open: bool = False,
        time_bars_only: bool = False,
        limit: int = 500,
    ) -> reports_commercial.CommercialRegister:
        self.calls.append("list_commercial")  # type: ignore[attr-defined]
        if not self.is_corr_controller:
            lines: list[reports_commercial.CommercialLine] = []
        else:
            lines = [
                line
                for line in self._commercial_lines.get(project, [])
                if (subtype is None or line.subtype == subtype)
                and (state is None or line.state == state)
                and (not only_open or line.state not in ("Closed", "Void"))
                and (not time_bars_only or line.time_bar_due is not None)
            ]
        return reports_commercial.CommercialRegister(
            scope=project,
            as_of="2026-10-20",
            lines=lines[:limit],
            totals=[],
            time_bars_running=sum(1 for line in lines if line.time_bar_state == "running"),
            time_bars_late=sum(1 for line in lines if line.time_bar_late),
        )

    def get_commercial(self, project: str, number: str) -> views_domain.CommercialView:
        self.calls.append("get_commercial")  # type: ignore[attr-defined]
        found = self._commercial.get(project, {}).get(number) if self.is_corr_controller else None
        if found is None:
            raise ItemNotFoundError(f"no commercial item {number!r} in scope {project!r}")
        return found

    def get_evidence_trail(
        self,
        project: str,
        number: str,
        *,
        as_of: date | None = None,
        depth: int = 2,
        max_nodes: int = 100,
    ) -> evidence.EvidenceTrail:
        self.calls.append("get_evidence_trail")  # type: ignore[attr-defined]
        self.trail_requests.append((number, as_of))
        found = self._trails.get(project, {}).get(number)
        if found is None:
            raise ItemNotFoundError(f"no item {number!r} in scope {project!r}")
        if as_of is not None and as_of.isoformat() > "2026-10-20":
            raise EvidenceDateError("the date is to come")
        return found

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


def _item_fields(number: str, subject: str, state: str, **more: object) -> dict[str, object]:
    """The fields of an ``ItemView`` for an outgoing item of a domain, with ``more`` over them."""
    fields: dict[str, object] = {
        "id": f"ID-{number}", "number": number, "subject": subject, "state": state,
        "direction": "out", "medium": "other", "received_via": "manual", "external_ref": None,
        "from_name": None, "from_party_id": None,
        "to": [views.RecipientView(name="Meridian", email="pm@meridian.test", party_id=None)],
        "cc": [], "sent_on": None, "received_on": None, "issued_on": None, "body": None,
        "confidentiality": "internal", "domain": None, "subtype": None, "thread_id": None,
        "thread_number": None, "responds_to_id": None, "responds_to_number": None,
        "superseded_by_id": None, "response_required": True, "response_due": None,
        "responded_on": None, "triaged_on": None, "triaged_by": None, "delivery": "none",
        "rendition_file_id": None, "version": 1,
    }  # fmt: skip
    return {**fields, **more}


def seed_domains(client: FakeCorrespondenceSupport, project: str = "P123") -> None:
    """Three RFIs (one answered in time with a cost impact and escalated, one overdue, one a
    draft), two Commercial notices (an early warning whose bar was met late, an agreed change
    notice) and the evidence trail of the early warning (the RFI it came from)."""
    clock = views.ClockView(
        id="CLK-R2", key="P123-RFI-0002-C01", item_id="ID-P123-RFI-0002",
        item_number="P123-RFI-0002", label="Answer required", kind="response_from_them",
        start_on="2026-10-05", duration_days=10, day_type="working", calendar="P123-default@1",
        warn_days=[3, 1], due_on="2026-10-19", state="running", effective_state="expired",
        days_left=-1, warned_level=None, paused_on=None, closed_on=None, closed_reason=None,
        owner=None, clause_id=None, restarts=0,
    )  # fmt: skip

    def rfi(number: str, subject: str, state: str, **more: object) -> views_domain.TechnicalView:
        fields: dict[str, object] = {
            **_item_fields(number, subject, state, domain="technical", subtype="rfi"),
            "question": f"Please confirm: {subject}", "proposed_solution": None,
            "discipline": "structural", "required_by": "2026-11-02",
            "potential_cost_impact": "unknown", "potential_schedule_impact": "unknown",
            "answer": None, "answered_on": None, "answer_cost_impact": None,
            "answer_schedule_impact": None, "answer_item_id": None, "answer_item_number": None,
            "answering_revision_id": None, "review_decision": None, "reviewed_on": None,
            "review_note": None,
        }  # fmt: skip
        return views_domain.TechnicalView(**{**fields, **more})  # type: ignore[arg-type]

    def log_line(view: views_domain.TechnicalView, **more: object) -> reports_technical.RfiLogLine:
        fields: dict[str, object] = {
            "id": view.id, "number": view.number, "subject": view.subject,
            "subtype": view.subtype or "", "discipline": view.discipline, "state": view.state,
            "raised_on": "2026-10-05", "issued_on": view.issued_on,
            "required_by": view.required_by, "answered_on": view.answered_on,
            "response_days": None, "on_time": None, "overdue": False, "days_overdue": None,
            "potential_cost_impact": view.potential_cost_impact,
            "potential_schedule_impact": view.potential_schedule_impact,
            "cost_impact": view.answer_cost_impact,
            "schedule_impact": view.answer_schedule_impact,
            "review_decision": view.review_decision, "confidentiality": "internal",
        }  # fmt: skip
        return reports_technical.RfiLogLine(**{**fields, **more})  # type: ignore[arg-type]

    answered = rfi(
        "P123-RFI-0001", "Beam B12 clashes with line 47", "Answered", issued_on="2026-10-05",
        answer="Re-route above the beam.", answered_on="2026-10-12", answer_cost_impact="yes",
        answer_schedule_impact="no", required_by="2026-10-19", potential_cost_impact="unknown",
        escalations=[views_domain.EscalationView(
            id="ID-P123-EW-0001", number="P123-EW-0001", subtype="early_warning", state="Draft"
        )],
    )  # fmt: skip
    overdue = rfi(
        "P123-RFI-0002", "Cable tray height", "Awaiting response", issued_on="2026-10-05",
        required_by="2026-10-19", potential_schedule_impact="yes", clocks=[clock],
    )  # fmt: skip
    draft = rfi("P123-RFI-0003", "Anchor bolt spacing", "Draft", discipline=None, required_by=None)
    client.add_rfi(project, answered, log_line(answered, response_days=7, on_time=True))
    client.add_rfi(project, overdue, log_line(overdue, overdue=True, days_overdue=1))
    client.add_rfi(project, draft, log_line(draft))

    def notice(number: str, subject: str, state: str, subtype: str, **more: object):  # type: ignore[no-untyped-def]
        fields: dict[str, object] = {
            **_item_fields(
                number, subject, state, domain="commercial", subtype=subtype,
                confidentiality="restricted",
            ),
            "contract_clause_id": None, "clause": "CT-1/20.1", "aware_on": "2026-10-12",
            "derived_from_id": None, "derived_from_number": None, "currency": "USD",
            "estimated_value": "12500.00", "estimated_hours": "240.0",
            "cost_code_impacts": [{"cost_code": "2.3.1", "amount": "12500.00"}],
            "schedule_impact_days": 3, "schedule_impact_note": None,
            "entitlement_basis": "Clause 20.1", "assessed_value": None, "assessed_on": None,
            "assessment_status": None, "assessment_note": None,
        }  # fmt: skip
        return views_domain.CommercialView(**{**fields, **more})  # type: ignore[arg-type]

    warning = notice(
        "P123-EW-0001", "Early warning: routing change", "Awaiting assessment", "early_warning",
        derived_from_id="ID-P123-RFI-0001", derived_from_number="P123-RFI-0001",
        issued_on="2026-10-30",
    )  # fmt: skip
    change = notice(
        "P123-CN-0001", "Change notice: cable tray", "Agreed", "change_notice",
        assessed_value="9000.00", assessed_on="2026-10-20", assessment_status="agreed",
        assessment_note="as stated", issued_on="2026-10-15",
    )  # fmt: skip

    def register_line(
        view: views_domain.CommercialView, **more: object
    ) -> reports_commercial.CommercialLine:
        fields: dict[str, object] = {
            "id": view.id, "number": view.number, "subject": view.subject,
            "subtype": view.subtype or "", "state": view.state, "direction": "out",
            "confidentiality": "restricted", "clause": view.clause, "aware_on": view.aware_on,
            "issued_on": view.issued_on, "time_bar_due": None, "time_bar_days_left": None,
            "time_bar_state": None, "time_bar_late": False, "currency": view.currency,
            "estimated_value": view.estimated_value, "assessed_value": view.assessed_value,
            "variance": None, "schedule_impact_days": view.schedule_impact_days,
            "assessment_status": view.assessment_status, "derived_from": view.derived_from_number,
        }  # fmt: skip
        return reports_commercial.CommercialLine(**{**fields, **more})  # type: ignore[arg-type]

    client.add_commercial(
        project, warning,
        register_line(
            warning, time_bar_due="2026-10-26", time_bar_days_left=-4, time_bar_state="met",
            time_bar_late=True,
        ),
    )  # fmt: skip
    client.add_commercial(
        project, change,
        register_line(
            change, time_bar_due="2026-11-09", time_bar_days_left=10, time_bar_state="met",
            variance="-3500.00",
        ),
    )  # fmt: skip

    def node(key: str, kind: str, state: str, title: str, depth: int, **more: object):  # type: ignore[no-untyped-def]
        fields: dict[str, object] = {
            "record_id": f"ID-{key}", "key": key, "title": title, "type": kind, "depth": depth,
            "parent_id": None, "via": None, "state": state, "voided": False,
            "created_on": "2026-10-12", "facts": {},
        }  # fmt: skip
        return evidence.EvidenceNode(**{**fields, **more})  # type: ignore[arg-type]

    via = evidence.EvidenceLink(
        link_id="LNK-1", relation="derived_from", label="derived from", direction="out",
        status="active", pin=None, note="escalated from P123-RFI-0001", since="2026-10-12",
    )  # fmt: skip
    client.add_trail(
        project,
        evidence.EvidenceTrail(
            scope=f"project:{project}", as_of="2026-10-20", root_id="ID-P123-EW-0001",
            nodes=[
                node("P123-EW-0001", "correspondence.CommercialItem", "Draft", warning.subject, 0),
                node(
                    "P123-RFI-0001", "correspondence.TechnicalItem", "Answered",
                    answered.subject, 1, parent_id="ID-P123-EW-0001", via=via,
                    facts={"cost_impact": "yes"},
                ),
            ],
            truncated=False,
        ),
        "P123-EW-0001",
    )  # fmt: skip
