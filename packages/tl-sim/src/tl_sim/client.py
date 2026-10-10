"""``HttpSimClient``: the ``SimClient`` that talks to the suite over its public interfaces.

Every write is a request to the REST API (``tl_api.client.ApiClient``) made with the actor's own
token, stamped with the simulated time (``X-TL-Effective-At``, FANOUT D5) and tagged
``source=sim:<run_id>``. ``propose`` goes to the MCP server through an ``McpCaller``. Nothing here
opens the ledger, a unit of work or a handler: the simulator dogfoods the open interfaces
(brief 29.1), which ``tests/test_contract_and_boundary.py`` enforces by reading the imports.

Keys. A simulation scope is ``project:sim-<run>``, and the numbering pattern's ``{project}`` takes
letters and digits only, so the suite cannot number records there. The client assigns the keys:
``SIM<RUN>-REC-0001``, ``-0002``, ... from counters the run keeps on disk. They fit the registered
pattern, so a ``#SIMR3FA91C-REC-0007`` in a post resolves to its record.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import httpx2
from tl_api.client import ApiClient
from tl_core.proposals.types import ProposalStatus, ProposalView
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.feed import PostToFeed
from tl_core.services.links import AddLink
from tl_core.services.psets import SetPsetValues
from tl_core.services.workflow import TransitionWorkflow

from tl_sim.clock import SimClock

EFFECTIVE_AT_HEADER = "X-TL-Effective-At"
RECORD_TYPE_CODE = "REC"  # the only record type in Phase 0 (core.Record)
MAX_QUERY = 5000  # the API's page limit
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
    def accept_proposal(self, proposal_id: str, *, roles: Sequence[str] = ()) -> ProposalView: ...
    def reject_proposal(self, proposal_id: str, reason: str) -> ProposalView: ...


@runtime_checkable
class ProposalDesk(Protocol):
    """What a person working the review queue needs on top of ``SimClient`` (not part of it)."""

    def pending_proposals(self) -> list[dict[str, Any]]: ...
    def accept_proposal(self, proposal_id: str) -> dict[str, Any]: ...
    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]: ...


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
    """A ``SimClient`` for one actor of one run."""

    def __init__(
        self,
        api: ApiLike,
        *,
        run_id: str,
        scope: str,
        clock: SimClock,
        keys: Keys,
        identity: str,
        roles: Sequence[str] = (),
        mcp: McpCaller | None = None,
    ) -> None:
        self._api = api
        self._source = f"sim:{run_id}"
        self._scope = scope
        self._clock = clock
        self._keys = keys
        self._identity = identity
        self._roles = list(roles)
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
            actor_roles=self._roles,
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

    def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._api.query_records(self._scope, q, limit=min(limit, MAX_QUERY))

    # --- the review queue, for the person who works it (``ProposalDesk``) -----------------------

    def pending_proposals(self) -> list[dict[str, Any]]:
        views = self._api.list_proposals(self._scope, status="pending", limit=PROPOSAL_LIMIT)
        return [view.model_dump(mode="json") for view in views]

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        self._clock.tick()
        return self._api.accept_proposal(proposal_id, roles=self._roles).model_dump(mode="json")

    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]:
        self._clock.tick()
        return self._api.reject_proposal(proposal_id, reason).model_dump(mode="json")
