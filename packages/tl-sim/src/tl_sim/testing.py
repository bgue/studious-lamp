"""An in-memory suite for tests: ``FakeWorld`` is a ``SimClient`` factory and a ``SimReader``.

It keeps records, links, posts and events in lists, numbers records the way ``Keys`` does, runs the
sample ``core.review`` workflow (Draft -> Review -> Approved -> Issued, back to Draft by ``reject``)
and refuses what the real suite refuses in those cases (``approve`` without a ``references`` link,
a transition from the wrong state). It stamps events with the simulated clock like the API does.
Actor and orchestrator tests use it so they need no server; the end-to-end tests use the real API.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from tl_core.services.errors import DuplicateLinkError, GuardFailedError, UnknownTransitionError
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    DuplicateSnapshotError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SourceFileError,
)

from tl_sim.actors.base import Rec, Recorder
from tl_sim.client import Keys, ProposeUnavailableError
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import ProposalRefusedError
from tl_sim.rng import actor_rng
from tl_sim.scenario import Scenario
from tl_sim.types import SimContext

REAL_TIME = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)  # "now", outside every played day
OPERATOR = "user:operator"  # who sets a schedule up in a test: a controller (the sim cannot)
WORKER = "svc:schedule"  # the worker that builds snapshots
SCANNER = "svc:scanner"
ACTIVITIES = (  # what a published snapshot of a test schedule holds
    ("A1000", "Issue P&IDs IFC"),
    ("A1100", "Procure valves"),
    ("A1230", "Fabricate spools"),
    ("A1990", "Hydrotest"),
)
WORKFLOW: dict[str, tuple[tuple[str, ...], str]] = {
    "submit": (("Draft",), "Review"),
    "approve": (("Review",), "Approved"),
    "issue": (("Approved",), "Issued"),
    "reject": (("Review", "Approved"), "Draft"),
}
# The fixture's `issue` needs the document controller role. A simulated person (a dev token) holds
# `user` only, so only a fake client built with that role passes it.
ROLE_GUARDED = {"issue": "document_controller"}


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
        self.schedule_rows: list[dict[str, Any]] = []
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
        recorded: datetime | None = None,
    ) -> None:
        self._seq += 1
        self.event_rows.append(
            {
                "seq": self._seq,
                "event_type": event_type,
                "actor": actor,
                "source": source,
                "effective_at": when.isoformat(),
                "recorded_at": (recorded or when).isoformat(),
                "stream_id": stream,
                "payload": payload or {},
            }
        )

    def record(self, record_id: str) -> dict[str, Any]:
        for record in self.record_rows:
            if record["id"] == record_id:
                return record
        raise LookupError(f"no record {record_id!r}")

    def define_schedule(
        self,
        code: str = "MAIN",
        title: str = "Main schedule",
        *,
        activities: Sequence[tuple[str, str]] = ACTIVITIES,
        published: bool = True,
    ) -> dict[str, Any]:
        """What a controller does before a run: define a schedule and (``published``) publish its
        first snapshot, built by the worker. The events are the operators' (``OPERATOR``,
        ``WORKER``), written in real time like the CLI and the worker write them."""
        schedule_id = f"id-{code}"
        row: dict[str, Any] = {
            "id": schedule_id,
            "code": code,
            "title": title,
            "snapshots": [],
            "refs": {},
        }
        self.schedule_rows.append(row)
        self.record_rows.append(self._row(schedule_id, code, "schedule.Schedule", title, None))
        self.emit("Record.Created", OPERATOR, "cli", REAL_TIME, schedule_id)
        self.emit("Schedule.Defined", OPERATOR, "cli", REAL_TIME, schedule_id)
        if published:
            snapshot = self.open_snapshot_row(row, OPERATOR, "cli", REAL_TIME)
            snapshot.update(state="Published", activities=list(activities), file=b"first")
            self.emit("ScheduleSnapshot.Built", WORKER, WORKER, REAL_TIME, snapshot["id"])
            self.emit("ScheduleSnapshot.MadeCurrent", OPERATOR, "cli", REAL_TIME, snapshot["id"])
            self.record(snapshot["id"])["status"] = "Published"
        return row

    def open_snapshot_row(
        self, schedule: dict[str, Any], actor: str, source: str, when: datetime
    ) -> dict[str, Any]:
        """The next snapshot of ``schedule`` as a record and a row (state ``Uploaded``)."""
        number = len(schedule["snapshots"]) + 1
        key = f"{schedule['code']}#{number}"
        snapshot: dict[str, Any] = {
            "id": f"id-{key}",
            "key": key,
            "number": number,
            "state": "Uploaded",
            "file": None,
            "filename": None,
            "activities": [],
        }
        schedule["snapshots"].append(snapshot)
        title = f"{schedule['title']} snapshot {number}"
        self.record_rows.append(
            self._row(snapshot["id"], key, "schedule.ScheduleSnapshot", title, None)
        )
        self.emit("Record.Created", actor, source, when, snapshot["id"])
        self.emit("ScheduleSnapshot.Defined", actor, source, when, snapshot["id"])
        return snapshot

    def _row(
        self, record_id: str, key: str, record_type: str, title: str, status: str | None
    ) -> dict[str, Any]:
        return {
            "id": record_id,
            "key": key,
            "type": record_type,
            "scope": self.scope,
            "title": title,
            "status": status,
            "psets": {},
            "voided": False,
            "version": 1,
        }

    def schedule_of(self, key: str, *, by: str = "code") -> dict[str, Any]:
        for row in self.schedule_rows:
            if row[by] == key:
                return row
        raise ScheduleNotFoundError(f"no schedule {key!r} in scope {self.scope!r}")

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

    def _write(
        self,
        event_type: str,
        stream: str,
        payload: dict[str, Any] | None = None,
        source: str | None = None,
        real_time: bool = False,
        actor: str | None = None,
    ) -> None:
        """Append an event. Like the suite: the simulator's own events and a decision made through
        the API carry simulated time (``effective_at`` is the clock); what the agent does over MCP
        (``real_time``) has ``effective_at`` equal to ``recorded_at``, the real clock."""
        simulated = self.clock.tick()
        src = source or f"sim:{self.world.run_id}"
        who = actor or self.identity
        if real_time:
            self.world.emit(event_type, who, src, REAL_TIME, stream, payload, REAL_TIME)
        else:
            recorded = None if src.startswith("sim:") else REAL_TIME
            self.world.emit(event_type, who, src, simulated, stream, payload, recorded)

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

    def create_tag(self, number: str, class_code: str, service: str) -> dict[str, Any]:
        """The ``TagDesk`` call: a tag is a record of type ``engineering.Tag``, keyed by number."""
        self.calls.append(("create_tag", (number,)))
        return self._new_tag(number, service)

    def rename_tag(self, record_id: str, new_number: str, reason: str) -> dict[str, Any]:
        """The ``TagDesk`` call: a new tag that supersedes the old one, which leaves service."""
        self.calls.append(("rename_tag", (record_id, new_number)))
        old = self.world.record(record_id)
        made = self._new_tag(new_number, old["title"])
        link_id = f"link-{len(self.world.link_rows) + 1}"
        self.world.link_rows.append(
            {
                "from_id": made["id"],
                "to_id": old["id"],
                "from_key": new_number,
                "to_key": old["key"],
                "view": {"link_id": link_id, "relation": "supersedes", "status": "active"},
            }
        )
        self._write("Link.Added", link_id)
        old["status"] = "Superseded"
        old["version"] += 1
        self._write("Workflow.Transitioned", record_id)
        return made

    def register_document(
        self, number: str, title: str, doc_type: str, discipline: str
    ) -> dict[str, Any]:
        """The ``DocumentDesk`` call: a document is a record of type ``documents.Document``."""
        self.calls.append(("register_document", (number,)))
        if any(r["key"] == number for r in self.world.record_rows):
            raise ValueError(f"document number {number!r} is already used")
        return self._new_record(number, "documents.Document", title, status="Registered")

    def start_revision(self, document_id: str, purpose: str) -> dict[str, Any]:
        """The ``DocumentDesk`` call: the next code after the document's revisions, as a draft."""
        self.calls.append(("start_revision", (document_id,)))
        document = self.world.record(document_id)
        made = [
            r
            for r in self.world.record_rows
            if r["type"] == "documents.Revision" and r["key"].startswith(f"{document['key']}@")
        ]
        code = chr(ord("A") + len(made))
        return self._new_record(
            f"{document['key']}@{code}",
            "documents.Revision",
            f"{document['key']} rev {code}",
            status="Draft",
        )

    def _new_record(
        self, key: str, record_type: str, title: str, *, status: str | None
    ) -> dict[str, Any]:
        record = {
            "id": f"id-{key}",
            "key": key,
            "type": record_type,
            "scope": self.world.scope,
            "title": title,
            "status": status,
            "psets": {},
            "voided": False,
            "version": 1,
        }
        self.world.record_rows.append(record)
        self._write("Record.Created", record["id"])
        return {"id": record["id"], "key": key, "version": 1}

    def _new_tag(self, number: str, title: str) -> dict[str, Any]:
        if any(r["key"] == number for r in self.world.record_rows):
            raise ValueError(f"tag number {number!r} is already used")
        record = {
            "id": f"id-{number}",
            "key": number,
            "type": "engineering.Tag",
            "scope": self.world.scope,
            "title": title,
            "status": None,
            "psets": {},
            "voided": False,
            "version": 1,
        }
        self.world.record_rows.append(record)
        self._write("Record.Created", record["id"])
        return {"id": record["id"], "key": number, "version": 1}

    # --- the schedule, for the person who sends the weekly update (``ScheduleDesk``) -----------

    def schedules(self) -> list[dict[str, Any]]:
        self.calls.append(("schedules", ()))
        out: list[dict[str, Any]] = []
        for row in self.world.schedule_rows:
            current = self._current(row)
            out.append(
                {
                    "id": row["id"],
                    "code": row["code"],
                    "title": row["title"],
                    "current_snapshot_number": None if current is None else current["number"],
                    "snapshot_count": len(row["snapshots"]),
                }
            )
        return out

    @staticmethod
    def _current(schedule: dict[str, Any]) -> dict[str, Any] | None:
        return next((s for s in schedule["snapshots"] if s["state"] == "Published"), None)

    def snapshots_of(self, code: str) -> list[dict[str, Any]]:
        self.calls.append(("snapshots_of", (code,)))
        schedule = self.world.schedule_of(code)
        return [
            {"id": s["id"], "key": s["key"], "number": s["number"], "state": s["state"]}
            for s in reversed(schedule["snapshots"])
        ]

    def current_activities(self, code: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self.calls.append(("current_activities", (code,)))
        schedule = self.world.schedule_of(code)
        current = self._current(schedule)
        if current is None:
            raise NoCurrentSnapshotError(f"schedule {code} has no published snapshot yet")
        return [{"activity_id": a, "name": n} for a, n in current["activities"]][:limit]

    def open_snapshot(self, schedule_id: str) -> dict[str, Any]:
        self.calls.append(("open_snapshot", (schedule_id,)))
        schedule = self.world.schedule_of(schedule_id, by="id")
        self.clock.tick()
        snapshot = self.world.open_snapshot_row(
            schedule, self.identity, f"sim:{self.world.run_id}", self.clock.now
        )
        return {"id": snapshot["id"], "key": snapshot["key"], "version": 2}

    def _snapshot(self, snapshot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        for schedule in self.world.schedule_rows:
            for snapshot in schedule["snapshots"]:
                if snapshot["id"] == snapshot_id:
                    return schedule, snapshot
        raise SnapshotNotFoundError(f"no snapshot {snapshot_id!r} in scope {self.world.scope!r}")

    def attach_snapshot_file(self, snapshot_id: str, filename: str, data: bytes) -> dict[str, Any]:
        self.calls.append(("attach_snapshot_file", (snapshot_id, filename)))
        _, snapshot = self._snapshot(snapshot_id)
        snapshot.update(file=data, filename=filename)
        # The file routes stamp the source `api` and real time; the scanner then processes it.
        file_id = f"file-{snapshot_id}"
        uploaded = {"file_id": file_id, "record_id": snapshot_id}
        self._write("File.Uploaded", file_id, uploaded, source="api", real_time=True)
        processed = {"file_id": file_id}
        self._write(
            "File.Processed", file_id, processed, source="api", real_time=True, actor=SCANNER
        )
        return {"id": snapshot_id, "size": len(data)}

    def start_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        self.calls.append(("start_snapshot", (snapshot_id,)))
        schedule, snapshot = self._snapshot(snapshot_id)
        if snapshot["file"] is None:
            raise SourceFileError(f"snapshot {snapshot['key']} has no XER file")
        digest = hashlib.sha256(snapshot["file"]).hexdigest()
        if any(
            other is not snapshot
            and other["file"] is not None
            and hashlib.sha256(other["file"]).hexdigest() == digest
            for other in schedule["snapshots"]
        ):
            raise DuplicateSnapshotError(f"this file is already snapshot of {schedule['code']}")
        self._write("ScheduleSnapshot.Queued", snapshot_id)
        return {"id": snapshot_id, "version": 3}

    def link_activity(self, record_id: str, schedule_id: str, activity_id: str) -> dict[str, Any]:
        self.calls.append(("link_activity", (record_id, schedule_id, activity_id)))
        schedule = self.world.schedule_of(schedule_id, by="id")
        current = self._current(schedule)
        if current is None:
            raise NoCurrentSnapshotError(f"schedule {schedule['code']} has no published snapshot")
        names = dict(current["activities"])
        if activity_id not in names:
            raise ActivityNotFoundError(f"no activity {activity_id!r} in the current snapshot")
        source = self.world.record(record_id)
        ref_id = schedule["refs"].get(activity_id)
        if ref_id is not None and any(
            link["from_id"] == record_id
            and link["to_id"] == ref_id
            and link["view"]["relation"] == "references"
            for link in self.world.link_rows
        ):
            raise DuplicateLinkError("a references link already exists between these records")
        made = ref_id is None
        if made:
            key = f"{schedule['code']}/{activity_id}"
            ref_id = f"id-{key}"
            schedule["refs"][activity_id] = ref_id
            self.world.record_rows.append(
                self.world._row(  # pyright: ignore[reportPrivateUsage]
                    ref_id,
                    key,
                    "schedule.ActivityRef",
                    f"{activity_id} {names[activity_id]}"[:200],
                    None,
                )
            )
            self._write("Record.Created", ref_id)
            self._write("ActivityRef.Defined", ref_id)
        target = self.world.record(str(ref_id))
        link_id = f"link-{len(self.world.link_rows) + 1}"
        self.world.link_rows.append(
            {
                "from_id": record_id,
                "to_id": target["id"],
                "from_key": source["key"],
                "to_key": target["key"],
                "view": {"link_id": link_id, "relation": "references", "status": "active"},
            }
        )
        self._write("Link.Added", link_id)
        return {"link_id": link_id, "version": 1, "ref_created": made}

    def propose(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("propose", (tool,)))
        if not self.can_propose:
            raise ProposeUnavailableError("the fake world was built without proposals")
        command: dict[str, Any] = {}
        if tool == "link_records":
            source = self._by_key(arguments["from_record"])
            target = self._by_key(arguments["to_record"])
            relation = arguments.get("relation") or "references"
            if any(
                link["from_id"] == source["id"]
                and link["to_id"] == target["id"]
                and link["view"]["relation"] == relation
                for link in self.world.link_rows
            ):
                raise ProposalRefusedError(
                    f"a {relation} link already exists between these records"
                )
            command = {"from_id": source["id"], "to_id": target["id"], "relation": relation}
        proposal_id = f"proposal-{len(self.world.proposal_rows) + 1}"
        self.world.proposal_rows.append(
            {
                "proposal_id": proposal_id,
                "agent": self.identity,
                "tool": tool,
                "status": "pending",
                "decided_by": None,
                "reason": None,
                "command": command,
            }
        )
        self._write(
            "Proposal.Created",
            proposal_id,
            {"agent": self.identity, "tool": tool},
            source=f"mcp:{self.identity.removeprefix('agent:')}",
            real_time=True,
        )
        return {"proposal": {"proposal_id": proposal_id, "status": "pending"}}

    def _by_key(self, key: str) -> dict[str, Any]:
        for record in self.world.record_rows:
            if record["key"] == key:
                return record
        raise ProposalRefusedError(f"no record {key!r}")

    # --- the review queue, for a person (the ProposalDesk of tl_sim.client) -----------------------

    def pending_proposals(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self.world.proposal_rows if p["status"] == "pending"]

    def _decide(self, proposal_id: str, status: str, reason: str | None) -> dict[str, Any]:
        for proposal in self.world.proposal_rows:
            if proposal["proposal_id"] == proposal_id and proposal["status"] == "pending":
                proposal.update(status=status, decided_by=self.identity, reason=reason)
                return proposal
        raise LookupError(f"no pending proposal {proposal_id!r}")

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        self.calls.append(("accept_proposal", (proposal_id,)))
        proposal = self._decide(proposal_id, "accepted", None)
        agent_source = f"mcp:{str(proposal['agent']).removeprefix('agent:')}"
        if proposal["tool"] == "link_records":
            command = proposal["command"]
            link_id = f"link-{len(self.world.link_rows) + 1}"
            source = self.world.record(command["from_id"])
            target = self.world.record(command["to_id"])
            self.world.link_rows.append(
                {
                    "from_id": source["id"],
                    "to_id": target["id"],
                    "from_key": source["key"],
                    "to_key": target["key"],
                    "view": {
                        "link_id": link_id,
                        "relation": command["relation"],
                        "status": "active",
                    },
                }
            )
            self._write("Link.Added", link_id, source=agent_source)
        self._write("Proposal.Accepted", proposal_id, source="api")
        return dict(proposal)

    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]:
        self.calls.append(("reject_proposal", (proposal_id,)))
        proposal = self._decide(proposal_id, "rejected", reason)
        self._write("Proposal.Rejected", proposal_id, source="api")
        return dict(proposal)

    def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Records of the scope. Only the filters the actors use are understood; others raise."""
        self.calls.append(("query", (q,)))
        found = [dict(r) for r in self.world.record_rows]
        for term in q.split():
            if term.startswith("title~"):
                needle = term.removeprefix("title~").strip('"').lower()
                found = [r for r in found if needle in r["title"].lower()]
            elif term.startswith("id:"):
                wanted = term.removeprefix("id:")
                found = [r for r in found if r["id"] == wanted]
            elif term.startswith("type:"):
                kind = term.removeprefix("type:")
                found = [r for r in found if r["type"] == kind]
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
        self.checked: list[str] = []

    def check(self, scenario: Scenario) -> None:
        self.checked.append(scenario.scenario)

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
