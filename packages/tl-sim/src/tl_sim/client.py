"""``HttpSimClient``: the ``SimClient`` that talks to the suite over its public interfaces.

Every write is a request to the REST API (``tl_api.client.ApiClient``) made with the actor's own
token, stamped with the simulated time (``X-TL-Effective-At``, FANOUT D5) and tagged
``source=sim:<run_id>``. ``propose`` goes to the MCP server through an ``McpCaller``. Nothing here
opens the ledger, a unit of work or a handler: the simulator dogfoods the open interfaces
(brief 29.1), which ``tests/test_contract_and_boundary.py`` enforces by reading the imports.

Keys. A simulation scope is ``project:sim-<run>``. The numbering pattern's ``{project}`` takes
letters and digits only, and the allocator drops the scope's hyphen, so IWP numbers come from the
allocator in this scope (``simrt1-IWP-PIP-0001``). Records keep the keys the client assigns:
``SIM<RUN>-REC-0001``, ``-0002``, ... from counters the run keeps on disk. They fit the registered
pattern, so a ``#SIMR3FA91C-REC-0007`` in a post resolves to its record.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx2
from tl_api.client import ApiClient
from tl_api.routes.constraints import ConstraintList
from tl_core.constraints.commands import ClearConstraint, RaiseConstraint
from tl_core.proposals.types import ProposalStatus, ProposalView
from tl_core.services.commands import Command, CommandResult, CreateRecord
from tl_core.services.feed import PostToFeed
from tl_core.services.links import AddLink
from tl_core.services.psets import SetPsetValues
from tl_core.services.workflow import TransitionWorkflow
from tl_mod_awp.commands import AddIwpScope, CreateIwp, CreateScopeItem, StartIwpDevelopment
from tl_mod_awp.iwp_views import IwpRow
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.handlers.technical import RaiseTechnical, SubmitTechnical
from tl_mod_correspondence.handlers.technical_flow import (
    AnswerTechnical,
    ReviewTechnicalAnswer,
)
from tl_mod_correspondence.reports_technical import RfiLog
from tl_mod_documents.handlers.documents import RegisterDocument
from tl_mod_documents.handlers.revisions import CreateRevision
from tl_mod_engineering.handlers.tags import CreateTag, RenameTag
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.snapshots import OpenScheduleSnapshot, StartScheduleSnapshot
from tl_mod_schedule.views import ActivityPage, ScheduleDetailView, ScheduleView

from tl_sim.clock import SimClock
from tl_sim.mcp_caller import McpUnavailableError

EFFECTIVE_AT_HEADER = "X-TL-Effective-At"
RECORD_TYPE_CODE = "REC"  # the only record type in Phase 0 (core.Record)
XER_CONTENT_TYPE = "application/octet-stream"  # a guess from ".xer" would be an XML type
MAX_QUERY = 5000  # the API's page limit
RFI_LIMIT = 500  # the RFI log's page; a simulation stays far below it
PROPOSAL_LIMIT = 500  # the proposals route's maximum (`le=500`); the queue is worked every day


class ProposeUnavailableError(Exception):
    """``propose`` was called but no MCP caller is wired (the proposals service is not on)."""


class McpCaller(Protocol):
    """Calls one tool of the suite's MCP server as the actor and returns its structured result."""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ApiLike(Protocol):
    """The ``ApiClient`` methods the simulator uses (a Protocol so tests can stand in)."""

    def create_record(self, cmd: CreateRecord) -> CommandResult: ...
    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult: ...
    def add_link(self, cmd: AddLink) -> CommandResult: ...
    def transition(self, cmd: TransitionWorkflow) -> CommandResult: ...
    def feed_post(self, cmd: PostToFeed) -> CommandResult: ...
    def create_tag(self, cmd: CreateTag) -> CommandResult: ...
    def rename_tag(self, cmd: RenameTag) -> CommandResult: ...
    def register_document(self, cmd: RegisterDocument) -> CommandResult: ...
    def create_revision(self, cmd: CreateRevision) -> CommandResult: ...
    def open_schedule_snapshot(self, cmd: OpenScheduleSnapshot) -> CommandResult: ...
    def start_schedule_snapshot(self, cmd: StartScheduleSnapshot) -> CommandResult: ...
    def link_activity(self, cmd: LinkActivity) -> CommandResult: ...
    def upload_file(
        self,
        scope: str,
        record_id: str,
        path: Path,
        *,
        slot: str | None = None,
        content_type: str | None = None,
    ) -> Any: ...
    def correspondence_command(self, name: str, cmd: Command) -> CommandResult: ...
    def list_rfis(self, project: str, *, limit: int = 500) -> RfiLog: ...
    def list_iwps(
        self, project: str, *, state: str | None = None, limit: int = 200
    ) -> list[IwpRow]: ...
    def list_constraints(
        self,
        project: str,
        *,
        subject: str | None = None,
        state: str | None = None,
        limit: int = 200,
    ) -> ConstraintList: ...
    def list_schedules(self, project: str) -> list[ScheduleView]: ...
    def get_schedule(self, project: str, code: str) -> ScheduleDetailView: ...
    def list_activities(
        self, project: str, code: str, *, snapshot: int | None = None, limit: int = 200
    ) -> ActivityPage: ...
    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None: ...
    def query_records(
        self, scope: str, q: str, *, limit: int = 500, offset: int = 0
    ) -> list[dict[str, Any]]: ...
    def list_proposals(
        self,
        scope: str,
        *,
        status: ProposalStatus | None = "pending",
        agent: str | None = None,
        limit: int = 200,
    ) -> list[ProposalView]: ...
    def accept_proposal(self, proposal_id: str) -> ProposalView: ...
    def reject_proposal(self, proposal_id: str, reason: str) -> ProposalView: ...


@runtime_checkable
class AwpDesk(Protocol):
    """What a workface planner needs on top of ``SimClient`` (not part of it): the path's areas."""

    def areas(self) -> list[str]: ...


@runtime_checkable
class MaterialsDesk(Protocol):
    """What a materials coordinator needs on top of ``SimClient`` (not part of it): the short
    take-off lines, the stock, and a proposal to reserve stock for a line."""

    def short_lines(self, *, limit: int = 50) -> list[dict[str, Any]]: ...
    def stock(self, *, limit: int = 200) -> list[dict[str, Any]]: ...
    def propose_reservation(
        self, lot: str, location: str, mto_line: str, qty: str
    ) -> dict[str, Any]: ...


@runtime_checkable
class ProposalDesk(Protocol):
    """What a person working the review queue needs on top of ``SimClient`` (not part of it)."""

    def pending_proposals(self) -> list[dict[str, Any]]: ...
    def accept_proposal(self, proposal_id: str) -> dict[str, Any]: ...
    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]: ...


@runtime_checkable
class TagDesk(Protocol):
    """What a person who keeps the tag list needs on top of ``SimClient`` (not part of it)."""

    def create_tag(self, number: str, class_code: str, service: str) -> dict[str, Any]: ...
    def rename_tag(self, record_id: str, new_number: str, reason: str) -> dict[str, Any]: ...


@runtime_checkable
class DocumentDesk(Protocol):
    """What a person who keeps the document register needs besides ``SimClient``."""

    def register_document(
        self, number: str, title: str, doc_type: str, discipline: str
    ) -> dict[str, Any]: ...
    def start_revision(self, document_id: str, purpose: str) -> dict[str, Any]: ...


@runtime_checkable
class ScheduleDesk(Protocol):
    """What a person who sends the weekly P6 update needs besides ``SimClient`` (P1-I4).

    Opening a snapshot, attaching the file and queueing the build are any signed-in person's acts
    (ADR-0015 section 7); defining a schedule and publishing a snapshot are a controller's, which a
    simulated person is not, so neither is here.
    """

    def schedules(self) -> list[dict[str, Any]]: ...
    def snapshots_of(self, code: str) -> list[dict[str, Any]]: ...
    def current_activities(self, code: str, *, limit: int = 200) -> list[dict[str, Any]]: ...
    def open_snapshot(self, schedule_id: str) -> dict[str, Any]: ...
    def attach_snapshot_file(
        self, snapshot_id: str, filename: str, data: bytes
    ) -> dict[str, Any]: ...
    def start_snapshot(self, snapshot_id: str) -> dict[str, Any]: ...
    def link_activity(
        self, record_id: str, schedule_id: str, activity_id: str
    ) -> dict[str, Any]: ...


@runtime_checkable
class TechnicalDesk(Protocol):
    """What a site engineer and the client's representative need besides ``SimClient`` (P1-I6).

    Raising, submitting, answering and accepting are any signed-in person's acts; issuing an RFI is
    a document controller's, which a simulated person is not, so it is not here.
    """

    def rfis(self) -> list[dict[str, Any]]: ...
    def raise_rfi(
        self, subject: str, question: str, discipline: str, required_by: str
    ) -> dict[str, Any]: ...
    def submit_rfi(self, rfi_id: str) -> dict[str, Any]: ...
    def answer_rfi(
        self, rfi_id: str, answer: str, cost_impact: str, schedule_impact: str
    ) -> dict[str, Any]: ...
    def accept_answer(self, rfi_id: str) -> dict[str, Any]: ...


OPEN_CONSTRAINT_STATES = ("Open", "Assigned")  # what a person may still clear (tl_core guard)


@runtime_checkable
class IwpDesk(Protocol):
    """What a person who builds IWPs and works their constraints needs besides ``SimClient``.

    Creating a package or a scope item, adding scope, starting development and raising or clearing
    a manual constraint are any signed-in person's acts; a simulated person does no sign-off or
    issue (those are the operators').
    """

    def iwps(self) -> list[dict[str, Any]]: ...
    def create_iwp(self, discipline: str, title: str) -> dict[str, Any]: ...
    def create_scope_item(
        self, commodity: str, description: str, qty: str, uom: str, est_hours: str
    ) -> dict[str, Any]: ...
    def add_scope(self, iwp_id: str, item_ids: list[str]) -> dict[str, Any]: ...
    def start_development(self, iwp_id: str) -> dict[str, Any]: ...
    def raise_constraint(
        self, subject_id: str, category: str, description: str
    ) -> dict[str, Any]: ...
    def open_constraints(self) -> list[dict[str, Any]]: ...
    def clear_constraint(self, constraint_id: str, reason: str) -> dict[str, Any]: ...


class Keys:
    """Hands out record keys from counters that live in the run state (mutated in place)."""

    def __init__(self, run_id: str, counters: dict[str, int]) -> None:
        self.prefix = f"SIM{run_id.upper()}"
        self.counters = counters

    def next(self, type_code: str = RECORD_TYPE_CODE) -> str:
        number = self.counters.get(type_code, 0) + 1
        self.counters[type_code] = number
        return f"{self.prefix}-{type_code}-{number:04d}"


def install_stamp(http: httpx2.Client, clock: SimClock) -> None:
    """Make every request of ``http`` carry the clock's current instant as the effective time."""

    def stamp(request: httpx2.Request) -> None:
        request.headers[EFFECTIVE_AT_HEADER] = clock.stamp()

    http.event_hooks["request"].append(stamp)


def connect(base_url: str, token: str, clock: SimClock, *, timeout: float = 30.0) -> ApiLike:
    """An ``ApiClient`` for one actor whose requests carry the simulated time."""
    http = httpx2.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    install_stamp(http, clock)
    return ApiClient(base_url, token, http=http)


class HttpSimClient:
    """A ``SimClient`` for one actor of one run.

    It sends no workflow roles and cannot be given any: the suite derives them from the account
    behind the actor's token (ADR-0013, addendum P1-SEC1). A simulated person's token is a dev token
    and carries the `user` role only, so a role-guarded transition is refused for it; a person who
    must pass one signs in as an account that holds the role.
    """

    def __init__(
        self,
        api: ApiLike,
        *,
        run_id: str,
        scope: str,
        clock: SimClock,
        keys: Keys,
        identity: str,
        mcp: McpCaller | None = None,
    ) -> None:
        self._api = api
        self._source = f"sim:{run_id}"
        self._scope = scope
        self._clock = clock
        self._keys = keys
        self._identity = identity
        self._mcp = mcp

    def _common(self) -> dict[str, Any]:
        # `actor` is required by the model and ignored by the API: the token's actor is recorded.
        return {"actor": self._identity, "source": self._source, "scope": self._scope}

    def _version(self, record_id: str) -> int:
        envelope = self._api.get_record_by_id(record_id)
        if envelope is None:
            raise LookupError(f"no record {record_id!r}")
        return int(envelope["version"])

    def create_record(
        self, *, record_type: str, title: str, psets: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._clock.tick()
        key = self._keys.next()
        cmd = CreateRecord(
            **self._common(), record_type=record_type, title=title, key=key, psets=psets or {}
        )
        result = self._api.create_record(cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    def set_psets(self, record_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """``values`` is ``{pset: {property: value}}``; one write per pset, in name order."""
        version = self._version(record_id)
        for pset in sorted(values):
            self._clock.tick()
            layer = "project" if pset.startswith("prj.") else "standard"
            cmd = SetPsetValues(
                **self._common(),
                stream_id=record_id,
                expected_version=version,
                pset=pset,
                layer=layer,
                values=values[pset],
            )
            version = self._api.set_pset_values(cmd).version
        return {"id": record_id, "version": version}

    def link(self, from_id: str, to_id: str, relation: str | None = None) -> dict[str, Any]:
        self._clock.tick()
        cmd = AddLink(**self._common(), from_id=from_id, to_id=to_id, relation=relation)
        result = self._api.add_link(cmd)
        return {"link_id": result.stream_id, "version": result.version}

    def transition(self, record_id: str, transition: str) -> dict[str, Any]:
        self._clock.tick()
        cmd = TransitionWorkflow(
            **self._common(),
            stream_id=record_id,
            expected_version=self._version(record_id),
            transition=transition,
        )
        result = self._api.transition(cmd)
        to_state = next(
            (
                e.payload.get("to_state")
                for e in result.events
                if e.event_type == "Workflow.Transitioned"
            ),
            None,
        )
        return {"id": record_id, "version": result.version, "state": to_state}

    def post(self, body: str) -> dict[str, Any]:
        self._clock.tick()
        result = self._api.feed_post(PostToFeed(**self._common(), body=body))
        return {"post_id": result.stream_id, "version": result.version}

    def propose(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._mcp is None:
            raise ProposeUnavailableError("no MCP caller is wired for this actor")
        self._clock.tick()
        return self._mcp.call_tool(tool, arguments)

    def areas(self) -> list[str]:
        """The CWA codes of the current path of construction, in path order (``AwpDesk``).

        The tool answers ``PathView | None``, so the structured answer may sit under ``result``; a
        null or empty path is no areas. A step whose area the viewer may not read has no code.
        """
        if self._mcp is None:
            raise McpUnavailableError("no MCP caller is wired for this actor")
        answer = self._mcp.call_tool(
            "path_of_construction", {"project": self._scope.removeprefix("project:")}
        )
        if "steps" not in answer and "result" in answer:
            answer = answer["result"] or {}
        return [str(step["cwa"]) for step in answer.get("steps") or [] if step.get("cwa")]

    def _rows(self, tool: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """The rows a list tool answers; its structured result sits under ``result``."""
        if self._mcp is None:
            raise McpUnavailableError("no MCP caller is wired for this actor")
        answer = self._mcp.call_tool(tool, arguments)
        return [dict(row) for row in answer.get("result") or []]

    def short_lines(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """The project's take-off lines that are short of stock (``MaterialsDesk``)."""
        arguments = {"project": self._project, "short_only": True, "limit": limit}
        return self._rows("list_mto_lines", arguments)

    def stock(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """The project's stock balances, one row per lot and location (``MaterialsDesk``)."""
        return self._rows("list_material_stock", {"project": self._project, "limit": limit})

    def propose_reservation(
        self, lot: str, location: str, mto_line: str, qty: str
    ) -> dict[str, Any]:
        """File a proposal to reserve ``qty`` of ``lot`` at ``location`` for ``mto_line``."""
        arguments = {
            "project": self._project,
            "lot": lot,
            "location": location,
            "mto_line": mto_line,
            "qty": qty,
        }
        return self.propose("propose_reservation", arguments)

    def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._api.query_records(self._scope, q, limit=min(limit, MAX_QUERY))

    # --- the tag list, for the person who keeps it (``TagDesk``) ---------------------------

    def create_tag(self, number: str, class_code: str, service: str) -> dict[str, Any]:
        """Create a tag. The registry checks the number against the numbering pattern."""
        self._clock.tick()
        cmd = CreateTag(**self._common(), number=number, class_code=class_code, service=service)
        result = self._api.create_tag(cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    def rename_tag(self, record_id: str, new_number: str, reason: str) -> dict[str, Any]:
        """Replace a tag by a new one with ``new_number``; the answer is the new tag."""
        self._clock.tick()
        cmd = RenameTag(**self._common(), stream_id=record_id, new_number=new_number, reason=reason)
        result = self._api.rename_tag(cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    # --- the document register, for the person who keeps it (``DocumentDesk``) ------------------

    def register_document(
        self, number: str, title: str, doc_type: str, discipline: str
    ) -> dict[str, Any]:
        """Register a document. The registry checks the number against the numbering pattern."""
        self._clock.tick()
        cmd = RegisterDocument(
            **self._common(), number=number, title=title, doc_type=doc_type, discipline=discipline
        )
        result = self._api.register_document(cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    def start_revision(self, document_id: str, purpose: str) -> dict[str, Any]:
        """Start the next revision of a document, as a draft; the answer is the revision."""
        self._clock.tick()
        cmd = CreateRevision(**self._common(), document_id=document_id, purpose=purpose)
        result = self._api.create_revision(cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    # --- the review queue, for the person who works it (``ProposalDesk``) -----------------------

    def pending_proposals(self) -> list[dict[str, Any]]:
        views = self._api.list_proposals(self._scope, status="pending", limit=PROPOSAL_LIMIT)
        return [view.model_dump(mode="json") for view in views]

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        self._clock.tick()
        return self._api.accept_proposal(proposal_id).model_dump(mode="json")

    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]:
        self._clock.tick()
        return self._api.reject_proposal(proposal_id, reason).model_dump(mode="json")

    # --- RFIs, for the site engineer and the client's representative (``TechnicalDesk``) --------

    def rfis(self) -> list[dict[str, Any]]:
        """The project's RFIs, newest number first: ``id, number, subject, state, ...``."""
        log = self._api.list_rfis(self._project, limit=RFI_LIMIT)
        return [line.model_dump(mode="json") for line in log.lines]

    def raise_rfi(
        self, subject: str, question: str, discipline: str, required_by: str
    ) -> dict[str, Any]:
        """Raise an RFI as a draft; the answer is the item (key = its number)."""
        self._clock.tick()
        cmd = RaiseTechnical(
            **self._common(),
            subtype="rfi",
            subject=subject,
            question=question,
            discipline=discipline,
            required_by=required_by,
            to=[Recipient(name="Client engineer", email="engineer@client.example")],
        )
        result = self._api.correspondence_command("RaiseTechnical", cmd)
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    def submit_rfi(self, rfi_id: str) -> dict[str, Any]:
        self._clock.tick()
        result = self._api.correspondence_command(
            "SubmitTechnical", SubmitTechnical(**self._common(), stream_id=rfi_id)
        )
        return {"id": rfi_id, "version": result.version}

    def answer_rfi(
        self, rfi_id: str, answer: str, cost_impact: str, schedule_impact: str
    ) -> dict[str, Any]:
        self._clock.tick()
        result = self._api.correspondence_command(
            "AnswerTechnical",
            AnswerTechnical(
                **self._common(),
                stream_id=rfi_id,
                answer=answer,
                cost_impact=cost_impact,
                schedule_impact=schedule_impact,
            ),
        )
        return {"id": rfi_id, "version": result.version}

    def accept_answer(self, rfi_id: str) -> dict[str, Any]:
        self._clock.tick()
        result = self._api.correspondence_command(
            "ReviewTechnicalAnswer",
            ReviewTechnicalAnswer(**self._common(), stream_id=rfi_id, decision="accepted"),
        )
        return {"id": rfi_id, "version": result.version}

    # --- IWPs and constraints, for the person who builds the packages (``IwpDesk``) -------------

    def _title_of(self, record_id: str) -> str:
        envelope = self._api.get_record_by_id(record_id)
        if envelope is None:
            raise LookupError(f"no record {record_id!r}")
        return str(envelope["title"])

    def iwps(self) -> list[dict[str, Any]]:
        """The project's IWPs by number: ``id, number, state`` (the list's rows)."""
        rows = self._api.list_iwps(self._project)
        found = [{"id": row.id, "number": row.number, "state": row.state} for row in rows]
        return sorted(found, key=lambda row: row["number"])

    def create_iwp(self, discipline: str, title: str) -> dict[str, Any]:
        """Create an IWP (the generic ``POST /commands/CreateIwp``); its number is the key."""
        self._clock.tick()
        cmd = CreateIwp(**self._common(), discipline=discipline, title=title)
        result = self._api.correspondence_command("CreateIwp", cmd)
        return {
            "id": result.stream_id,
            "key": result.key,
            "title": self._title_of(result.stream_id),
        }

    def create_scope_item(
        self, commodity: str, description: str, qty: str, uom: str, est_hours: str
    ) -> dict[str, Any]:
        """Create a scope item (``POST /commands/CreateScopeItem``); title = description."""
        self._clock.tick()
        cmd = CreateScopeItem(
            **self._common(),
            commodity=commodity,
            description=description,
            qty=qty,
            uom=uom,
            est_hours=est_hours,
        )
        result = self._api.correspondence_command("CreateScopeItem", cmd)
        return {
            "id": result.stream_id,
            "key": result.key,
            "title": self._title_of(result.stream_id),
        }

    def add_scope(self, iwp_id: str, item_ids: list[str]) -> dict[str, Any]:
        """Add scope items to an IWP (``POST /commands/AddIwpScope``), in one command."""
        self._clock.tick()
        cmd = AddIwpScope(**self._common(), iwp=iwp_id, items=list(item_ids))
        result = self._api.correspondence_command("AddIwpScope", cmd)
        return {"id": iwp_id, "version": result.version}

    def start_development(self, iwp_id: str) -> dict[str, Any]:
        """Draft to In development (``POST /commands/StartIwpDevelopment``)."""
        self._clock.tick()
        cmd = StartIwpDevelopment(**self._common(), iwp=iwp_id)
        result = self._api.correspondence_command("StartIwpDevelopment", cmd)
        return {"id": iwp_id, "version": result.version}

    def raise_constraint(self, subject_id: str, category: str, description: str) -> dict[str, Any]:
        """Raise a manual blocking constraint on a ready-phase record (``RaiseConstraint``).

        The raising person is the owner (a manual constraint needs one). The command is validated
        from a dict: ``category`` is a literal in the model, and the model's validator (not the
        type checker) is what refuses a bad one."""
        self._clock.tick()
        cmd = RaiseConstraint.model_validate(
            {
                **self._common(),
                "owner": self._identity,
                "subject": subject_id,
                "phase": "ready",
                "severity": "blocking",
                "category": category,
                "description": description,
            }
        )
        result = self._api.correspondence_command("RaiseConstraint", cmd)
        return {
            "id": result.stream_id,
            "key": result.key,
            "title": self._title_of(result.stream_id),
        }

    def open_constraints(self) -> list[dict[str, Any]]:
        """The project's constraints in state Open or Assigned, by key: ``id, key, subject_id``."""
        rows = self._api.list_constraints(self._project).rows
        found = [
            {"id": row.id, "key": row.key, "subject_id": row.subject_id}
            for row in rows
            if row.state in OPEN_CONSTRAINT_STATES
        ]
        return sorted(found, key=lambda row: row["key"])

    def clear_constraint(self, constraint_id: str, reason: str) -> dict[str, Any]:
        """Clear an open or assigned constraint (``POST /commands/ClearConstraint``)."""
        self._clock.tick()
        cmd = ClearConstraint(**self._common(), constraint=constraint_id, reason=reason)
        result = self._api.correspondence_command("ClearConstraint", cmd)
        return {"id": constraint_id, "version": result.version}

    # --- the schedule, for the person who sends the weekly update (``ScheduleDesk``) -------------

    @property
    def _project(self) -> str:
        return self._scope.removeprefix("project:")

    def schedules(self) -> list[dict[str, Any]]:
        """The project's schedules: ``id, code, title, current_snapshot_number, snapshot_count``."""
        return [view.model_dump(mode="json") for view in self._api.list_schedules(self._project)]

    def snapshots_of(self, code: str) -> list[dict[str, Any]]:
        """The snapshots of one schedule, newest number first: ``number, state, key, ...``."""
        detail = self._api.get_schedule(self._project, code)
        return [view.model_dump(mode="json") for view in detail.snapshots]

    def current_activities(self, code: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """The first ``limit`` activities of the current snapshot, in the snapshot's order."""
        page = self._api.list_activities(self._project, code, limit=limit)
        return [asdict(row) for row in page.rows]

    def open_snapshot(self, schedule_id: str) -> dict[str, Any]:
        """Open the next snapshot of the schedule; the answer is its record (key ``CODE#n``)."""
        self._clock.tick()
        result = self._api.open_schedule_snapshot(
            OpenScheduleSnapshot(**self._common(), schedule_id=schedule_id)
        )
        return {"id": result.stream_id, "key": result.key, "version": result.version}

    def attach_snapshot_file(self, snapshot_id: str, filename: str, data: bytes) -> dict[str, Any]:
        """Upload ``data`` as the snapshot's XER file (slot ``xer``)."""
        self._clock.tick()
        with tempfile.TemporaryDirectory(prefix="tl-sim-") as scratch:
            path = Path(scratch) / filename
            path.write_bytes(data)
            self._api.upload_file(
                self._scope, snapshot_id, path, slot="xer", content_type=XER_CONTENT_TYPE
            )
        return {"id": snapshot_id, "size": len(data)}

    def start_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """Queue the build of the snapshot (the worker builds it, a controller publishes it)."""
        self._clock.tick()
        result = self._api.start_schedule_snapshot(
            StartScheduleSnapshot(**self._common(), snapshot_id=snapshot_id)
        )
        return {"id": snapshot_id, "version": result.version}

    def link_activity(self, record_id: str, schedule_id: str, activity_id: str) -> dict[str, Any]:
        """Link a record to an activity by its P6 id. ``ref_created`` says whether this made the
        activity's reference record (the first link to that activity of the schedule)."""
        self._clock.tick()
        result = self._api.link_activity(
            LinkActivity(
                **self._common(),
                from_id=record_id,
                schedule_id=schedule_id,
                activity_id=activity_id,
            )
        )
        made = [e for e in result.events if e.event_type == "Record.Created"]
        return {
            "link_id": result.stream_id,
            "version": result.version,
            "ref_created": bool(made),
        }
