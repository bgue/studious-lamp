"""An in-memory suite for tests: ``FakeWorld`` is a ``SimClient`` factory and a ``SimReader``.

It keeps records, links, posts and events in lists, numbers records the way ``Keys`` does, runs the
sample ``core.review`` workflow (Draft -> Review -> Approved -> Issued, back to Draft by ``reject``)
and refuses what the real suite refuses in those cases (``approve`` without a ``references`` link,
a transition from the wrong state). It stamps events with the simulated clock like the API does.
Actor and orchestrator tests use it so they need no server; the end-to-end tests use the real API.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from tl_core.services.errors import GuardFailedError, UnknownTransitionError

from tl_sim.actors.base import Rec, Recorder
from tl_sim.client import Keys
from tl_sim.clock import SimClock
from tl_sim.rng import actor_rng
from tl_sim.types import SimContext

WORKFLOW: dict[str, tuple[tuple[str, ...], str]] = {
    "submit": (("Draft",), "Review"),
    "approve": (("Review",), "Approved"),
    "issue": (("Approved",), "Issued"),
    "reject": (("Review", "Approved"), "Draft"),
}
ROLE_GUARDED = {"issue": "manager"}


class FakeWorld:
    """One run's scope held in memory. ``client(identity, clock)`` gives an actor its view."""

    def __init__(self, run_id: str, scope: str) -> None:
        self.run_id = run_id
        self.scope = scope
        self.keys = Keys(run_id, {})  # a standalone world numbers its own records
        self.record_rows: list[dict[str, Any]] = []
        self.link_rows: list[dict[str, Any]] = []
        self.post_rows: list[dict[str, Any]] = []
        self.event_rows: list[dict[str, Any]] = []
        self.proposal_rows: list[dict[str, Any]] = []
        self._seq = 0

    # --- the store -------------------------------------------------------------------------

    def emit(
        self,
        event_type: str,
        actor: str,
        source: str,
        when: datetime,
        stream: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._seq += 1
        self.event_rows.append(
            {
                "seq": self._seq,
                "event_type": event_type,
                "actor": actor,
                "source": source,
                "effective_at": when.isoformat(),
                "recorded_at": when.isoformat(),
                "stream_id": stream,
                "payload": payload or {},
            }
        )

    def record(self, record_id: str) -> dict[str, Any]:
        for record in self.record_rows:
            if record["id"] == record_id:
                return record
        raise LookupError(f"no record {record_id!r}")

    def client(
        self,
        identity: str,
        clock: SimClock,
        keys: Keys | None = None,
        *,
        roles: Sequence[str] = (),
        propose: bool = False,
    ) -> FakeClient:
        return FakeClient(self, identity, clock, keys or self.keys, tuple(roles), propose)

    # --- the SimReader side -----------------------------------------------------------------

    def records(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.record_rows]

    def links(self, record_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for link in self.link_rows:
            if link["from_id"] == record_id:
                out.append({**link["view"], "direction": "out", "other_key": link["to_key"]})
            elif link["to_id"] == record_id:
                out.append({**link["view"], "direction": "in", "other_key": link["from_key"]})
        return out

    def posts(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self.post_rows]

    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self.event_rows]

    def proposals(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self.proposal_rows]


class FakeClient:
    """A ``SimClient`` over a ``FakeWorld``. Each write advances the clock like the real client."""

    def __init__(
        self,
        world: FakeWorld,
        identity: str,
        clock: SimClock,
        keys: Keys,
        roles: tuple[str, ...],
        can_propose: bool,
    ) -> None:
        self.world = world
        self.identity = identity
        self.clock = clock
        self.keys = keys
        self.roles = roles
        self.can_propose = can_propose
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _write(self, event_type: str, stream: str, payload: dict[str, Any] | None = None) -> None:
        when = self.clock.tick()
        self.world.emit(
            event_type, self.identity, f"sim:{self.world.run_id}", when, stream, payload
        )

    def create_record(
        self, *, record_type: str, title: str, psets: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("create_record", (title,)))
        key = self.keys.next()
        record = {
            "id": f"id-{key}",
            "key": key,
            "type": record_type,
            "scope": self.world.scope,
            "title": title,
            "status": None,
            "psets": dict(psets or {}),
            "voided": False,
            "version": 1,
        }
        self.world.record_rows.append(record)
        self._write("Record.Created", record["id"])
        return {"id": record["id"], "key": key, "version": 1}

    def set_psets(self, record_id: str, values: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("set_psets", (record_id,)))
        record = self.world.record(record_id)
        for pset in sorted(values):
            node: dict[str, Any] = record["psets"]
            for segment in pset.split("."):
                node = node.setdefault(segment, {})
            node.update(values[pset])
            record["version"] += 1
            self._write("Pset.ValuesSet", record_id)
        return {"id": record_id, "version": record["version"]}

    def link(self, from_id: str, to_id: str, relation: str | None = None) -> dict[str, Any]:
        self.calls.append(("link", (from_id, to_id, relation)))
        source, target = self.world.record(from_id), self.world.record(to_id)
        link_id = f"link-{len(self.world.link_rows) + 1}"
        self.world.link_rows.append(
            {
                "from_id": from_id,
                "to_id": to_id,
                "from_key": source["key"],
                "to_key": target["key"],
                "view": {
                    "link_id": link_id,
                    "relation": relation or "references",
                    "status": "active",
                },
            }
        )
        self._write("Link.Added", link_id)
        return {"link_id": link_id, "version": 1}

    def transition(self, record_id: str, transition: str) -> dict[str, Any]:
        self.calls.append(("transition", (record_id, transition)))
        record = self.world.record(record_id)
        if transition not in WORKFLOW:
            raise UnknownTransitionError(f"no transition {transition!r}")
        sources, target = WORKFLOW[transition]
        state = record["status"] or "Draft"
        if state not in sources:
            raise UnknownTransitionError(  # the real engine's answer to a wrong-state request
                f"transition {transition!r} cannot start in state {state!r}"
            )
        if transition == "approve" and not any(
            link["from_id"] == record_id and link["view"]["relation"] == "references"
            for link in self.world.link_rows
        ):
            raise GuardFailedError("approve needs a references link", [])
        role = ROLE_GUARDED.get(transition)
        if role is not None and role not in self.roles:
            raise GuardFailedError(f"{transition} needs the {role} role", [])
        record["status"] = target
        record["version"] += 1
        self._write("Workflow.Transitioned", record_id)
        return {"id": record_id, "version": record["version"], "state": target}

    def post(self, body: str) -> dict[str, Any]:
        self.calls.append(("post", (body,)))
        post_id = f"post-{len(self.world.post_rows) + 1}"
        self.world.post_rows.append(
            {"id": post_id, "actor": self.identity, "body": body, "retracted": False}
        )
        self._write("Feed.Posted", post_id, {"body": body})
        return {"post_id": post_id, "version": 1}

    def propose(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("propose", (tool,)))
        if not self.can_propose:
            from tl_sim.client import ProposeUnavailableError

            raise ProposeUnavailableError("the fake world was built without proposals")
        proposal_id = f"proposal-{len(self.world.proposal_rows) + 1}"
        self.world.proposal_rows.append(
            {"id": proposal_id, "agent": self.identity, "tool": tool, "arguments": arguments}
        )
        self._write("Proposal.Created", proposal_id, {"agent": self.identity, "tool": tool})
        return {"proposal_id": proposal_id}

    def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Records of the scope. Only the filters the actors use are understood; others raise."""
        self.calls.append(("query", (q,)))
        found = [dict(r) for r in self.world.record_rows]
        for term in q.split():
            if term.startswith("title~"):
                needle = term.removeprefix("title~").strip('"').lower()
                found = [r for r in found if needle in r["title"].lower()]
            elif term.startswith("status:"):
                want = term.removeprefix("status:")
                found = [r for r in found if (r["status"] or "null") == want]
            else:
                raise ValueError(f"FakeClient.query does not understand {term!r}")
        return sorted(found, key=lambda r: r["key"])[:limit]


class FakeConnector:
    """A ``Connector`` over one ``FakeWorld``; the world is created with the run's first client."""

    def __init__(self, run_id: str, *, propose: bool = False) -> None:
        self.world = FakeWorld(run_id, f"project:sim-{run_id}")
        self.propose = propose
        self.provisioned: list[str] = []

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        self.provisioned = list(identities)
        return {identity: f"token-{identity}" for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> FakeClient:
        return self.world.client(identity, clock, keys, propose=self.propose)

    def reader(self, tokens: dict[str, str]) -> FakeWorld:
        return self.world


def make_context(
    world: FakeWorld,
    identity: str,
    *,
    keys: Keys | None = None,
    now: datetime | None = None,
    seed: int = 1,
    day: int = 0,
    propose: bool = False,
) -> SimContext:
    """A context for one actor step over ``world`` (a Monday 07:00 unless ``now`` is given)."""
    moment = now or datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
    return SimContext(
        run_id=world.run_id,
        scope=world.scope,
        now=moment,
        rng=actor_rng(seed, identity, day),
        client=world.client(identity, SimClock(moment), keys, propose=propose),
    )


def seed_lines(world: FakeWorld, count: int = 3, keys: Keys | None = None) -> list[Rec]:
    """``count`` lines ``Line 6-CS-100n`` in the world, written by the orchestrator."""
    ctx = make_context(world, "user:sim-orchestrator", keys=keys)
    recorder = Recorder(ctx, "user:sim-orchestrator")
    return [recorder.create(f"Line 6-CS-{1000 + n}") for n in range(1, count + 1)]
