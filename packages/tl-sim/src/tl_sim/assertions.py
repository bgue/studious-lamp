"""``sim_assert``: compare what the scenario intended with what the suite holds (brief 29.5).

The ground-truth log says what the actors did and expected; the reader says what the public API
returns now (the ``cur_*`` projections and the event pager). The two must agree:

| Intent | Check |
|---|---|
| ``record.created`` | a record with that key exists, with the expected title, type and not voided |
| ``pset.set`` | the latest intended value of each property is the stored one |
| ``link.added`` | an active link of that relation leaves the ``from`` record for ``to`` |
| ``workflow.transitioned`` | the latest intended state of each record is its status |
| ``post.created`` | a live post by that author with that body exists (once per intended post) |
| ``snapshot.queued`` | that actor queued the snapshot's build (``ScheduleSnapshot.Queued``) |
| ``proposal.created`` | a proposal by that agent for that tool exists (once per intended one) |
| ``proposal.accepted`` / ``rejected`` | that person decided such a proposal that way (a link too) |

Each of those is also checked against the ledger event that fulfilled it: the actor that wrote
that record, pset value, link, transition, post or proposal must be the actor the log names
(``actor_mismatch``). The check fails closed: an empty log, or a run that checked nothing, is a
failure, not a pass.

Time: the simulator's own events (``sim:<run>``) carry simulated time and must fall on a played day.
An accepted proposal's effect and the decision, made through the API with the header, do too and
are checked the same way; the agent's own ``Proposal.Created`` is made over MCP and has real time
(``effective_at`` equal to ``recorded_at``), as has a decision taken at the CLI, so both are exempt.

A run must not pass by doing nothing. ``Expected`` says which actors were enabled and bound to
act: an assistant that is guaranteed at least one proposal a day but made none, or an approver
who decided nothing about the proposals that were made, is ``actor_silent``.

Operators. A scenario may name the people and services that set the run up by hand or work beside
it (``Scenario.operators``: the controller who defines and publishes a schedule, the worker that
builds it). What they wrote is setup, not simulation, but only setup of a schedule is excused: the
events of the schedule module (``OPERATOR_EVENTS``), ``Record.Created`` of a ``schedule.*`` record,
``Workflow.Transitioned`` and ``File.*`` on the stream of a ``schedule.*`` record, and
``Link.Flagged`` / ``Link.Repinned`` written by ``svc:schedule``. Any other event of an operator,
and any record of another type, is judged like a simulated actor's. The report counts what was
excused (``excused``). A file event of anyone else must be on a record the log names (or
one an operator made): a file cannot be attached to a record nobody intended.

Four more checks catch what the scenario did not intend: the scope holds no record the log does
not name, every event in the scope was written by the simulator (``source`` ``sim:<run>``, or an
MCP proposal, by a ``user:sim-*`` or ``agent:sim-*`` actor), and every simulator event carries a
simulated time on a day that was played (``effective_at``, FANOUT D5).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from tl_sim import groundtruth as gt
from tl_sim.reader import SimReader
from tl_sim.types import GroundTruth

DECISION_EVENTS = frozenset({"Proposal.Accepted", "Proposal.Rejected", "Proposal.Failed"})
#: A file upload goes through the file routes, which stamp the source ``api`` and real time, and the
#: scanner (a service of the suite) processes it.
FILE_EVENTS = frozenset({"File.Uploaded", "File.Processed"})
SCANNER = "svc:scanner"
QUEUED_EVENT = "ScheduleSnapshot.Queued"
SCHEDULE_TYPES = "schedule."  # the record types of the schedule module
SERVICE = "svc:schedule"
#: The events of the schedule module, which an operator (a controller, the worker) writes.
OPERATOR_EVENTS = frozenset(
    {
        "Schedule.Defined",
        "Schedule.SnapshotPublished",
        "Schedule.OrphansChecked",
        "ScheduleSnapshot.Defined",
        "ScheduleSnapshot.Queued",
        "ScheduleSnapshot.BuildStarted",
        "ScheduleSnapshot.BuildFailed",
        "ScheduleSnapshot.Built",
        "ScheduleSnapshot.Rejected",
        "ScheduleSnapshot.MadeCurrent",
        "ActivityRef.Defined",
        "ActivityRef.PresenceChanged",
    }
)
#: Written by an operator on the stream of a ``schedule.*`` record.
OPERATOR_STREAM_EVENTS = frozenset({"Record.Created", "Workflow.Transitioned", *FILE_EVENTS})
#: The flags the module's worker writes on links to activities.
OPERATOR_LINK_EVENTS = frozenset({"Link.Flagged", "Link.Repinned"})
SIM_ACTORS = ("user:sim-", "agent:sim-")
#: What an ``agent:*`` actor may write: proposals, posts, and the link suggestions a post makes.
AGENT_EVENTS = frozenset({"Proposal.Created", "Feed.Posted", "Link.Suggested"})
ENVELOPE_FIELDS = {"title": "title", "record_type": "type", "voided": "voided", "status": "status"}


@dataclass(frozen=True)
class Failure:
    check: str  # an intent, or "unexpected_record", "event_source", "event_time"
    ref: str
    field: str
    expected: Any
    actual: Any

    def line(self) -> str:
        return (
            f"{self.check} {self.ref} {self.field}: "
            f"expected {self.expected!r}, found {self.actual!r}"
        )


@dataclass(frozen=True)
class Expected:
    """Who was enabled and must have acted. Defaults: nobody (``sim_assert`` of a plain run)."""

    proposals: bool = False  # the assistant is on and guaranteed at least one proposal a day
    decisions: bool = False  # the approver is on
    operators: frozenset[str] = frozenset()  # setup by hand or beside the run; see the docstring
    days_played: int = 0


@dataclass
class AssertionReport:
    checked: int = 0
    failures: list[Failure] = field(default_factory=list[Failure])
    counts: dict[str, int] = field(default_factory=dict[str, int])  # intents seen in the log
    excused: int = 0  # records and events left alone because an operator wrote them

    @property
    def ok(self) -> bool:
        return not self.failures


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-12)
    return expected == actual


def _dig(root: dict[str, Any], path: str) -> Any:
    node: Any = root
    for segment in path.split("."):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]  # pyright: ignore[reportUnknownVariableType]
    return node  # pyright: ignore[reportUnknownVariableType]


def created_refs(truth: list[GroundTruth]) -> set[str]:
    """The keys of the records the log says were made."""
    return {item.ref for item in truth if item.intent == gt.RECORD_CREATED}


def latest(truth: list[GroundTruth], intent: str) -> list[tuple[str, str, Any]]:
    """The last intended value of every ``(ref, field)`` of ``intent``, in log order."""
    final: dict[tuple[str, str], Any] = {}
    for item in truth:
        if item.intent == intent:
            for name, value in item.expect.items():
                final[(item.ref, name)] = value
    return [(ref, name, value) for (ref, name), value in final.items()]


def run_assertions(
    truth: list[GroundTruth],
    reader: SimReader,
    *,
    run_id: str,
    played: Collection[date],
    expected: Expected | None = None,
) -> AssertionReport:
    """Check every intent in ``truth`` against ``reader``; ``played`` holds the simulated dates."""
    expected = expected or Expected()
    report = AssertionReport(counts=dict(Counter(item.intent for item in truth)))
    if not truth:  # nothing intended is nothing proved
        report.failures.append(Failure("empty_ground_truth", "-", "log", "at least one intent", 0))
        return report

    def fail(check: str, ref: str, name: str, expected: Any, actual: Any) -> None:
        report.failures.append(Failure(check, ref, name, expected, actual))

    def check(ok: bool, check_name: str, ref: str, name: str, expected: Any, actual: Any) -> None:
        report.checked += 1
        if not ok:
            fail(check_name, ref, name, expected, actual)

    by_key = {str(r["key"]): r for r in reader.records()}
    events = reader.events()
    creator: dict[str, str] = {}  # stream id of a record -> who wrote its Record.Created
    file_record: dict[str, str] = {}  # file id -> the id of the record it was uploaded to
    writers: dict[tuple[str, str], set[str]] = {}  # (stream id, event type) -> actors
    posted: Counter[tuple[str, str]] = Counter()  # (actor, body) of Feed.Posted
    proposed: Counter[tuple[str, str, str]] = Counter()  # (actor, agent, tool) of Proposal.Created
    for event in events:
        writers.setdefault((str(event["stream_id"]), str(event["event_type"])), set()).add(
            str(event["actor"])
        )
        payload = event.get("payload") or {}
        if event["event_type"] == "Record.Created":
            creator[str(event["stream_id"])] = str(event["actor"])
        if event["event_type"] == "File.Uploaded":  # a file's events are on the file's stream
            file_record[str(payload.get("file_id"))] = str(payload.get("record_id"))
        if event["event_type"] == "Feed.Posted":
            posted[(str(event["actor"]), str(payload.get("body")))] += 1
        elif event["event_type"] == "Proposal.Created":
            key = (str(event["actor"]), str(payload.get("agent")), str(payload.get("tool")))
            proposed[key] += 1

    def written_by(item: GroundTruth, stream: str | None, event_type: str) -> None:
        """The event of ``event_type`` on ``stream`` was written by the actor the log names."""
        found = writers.get((stream, event_type), set()) if stream is not None else set()
        check(
            item.actor in found,
            "actor_mismatch",
            item.ref,
            f"{item.intent} by",
            item.actor,
            sorted(found) or None,
        )

    type_of = {str(r["id"]): str(r["type"]) for r in by_key.values()}
    intended = {str(by_key[ref]["id"]) for ref in created_refs(truth) if ref in by_key} | {
        stream for stream, actor in creator.items() if actor in expected.operators
    }

    def record_of(event: dict[str, Any]) -> str:
        """The record an event is about: a file's events are on the file, which belongs to one."""
        stream = str(event["stream_id"])
        return file_record.get(stream, "") if event["event_type"] in FILE_EVENTS else stream

    def operator_event(event: dict[str, Any]) -> bool:
        """An event of the schedule setup that an operator may write (see the module docstring)."""
        kind = str(event["event_type"])
        if kind in OPERATOR_EVENTS:
            return True
        if kind in OPERATOR_STREAM_EVENTS:
            return type_of.get(record_of(event), "").startswith(SCHEDULE_TYPES)
        return kind in OPERATOR_LINK_EVENTS and event["actor"] == SERVICE

    # --- records ---------------------------------------------------------------------------
    created = {item.ref for item in truth if item.intent == gt.RECORD_CREATED}
    for item in truth:
        if item.intent != gt.RECORD_CREATED:
            continue
        record = by_key.get(item.ref)
        check(record is not None, item.intent, item.ref, "exists", True, record is not None)
        if record is None:
            continue
        for name, value in item.expect.items():
            actual = record.get(ENVELOPE_FIELDS.get(name, name))
            check(_same(value, actual), item.intent, item.ref, name, value, actual)
        written_by(item, str(record["id"]), "Record.Created")
    for key in sorted(set(by_key) - created):
        if creator.get(str(by_key[key]["id"])) in expected.operators and str(
            by_key[key]["type"]
        ).startswith(SCHEDULE_TYPES):
            report.excused += 1  # a schedule made by hand before or beside the run
            continue
        fail("unexpected_record", key, "key", None, by_key[key].get("title"))
        report.checked += 1

    # --- psets and workflow state: the latest intent wins ---------------------------------------
    for ref, name, value in latest(truth, gt.PSET_SET):
        record = by_key.get(ref)
        actual = _dig(record, name) if record is not None else None
        check(_same(value, actual), gt.PSET_SET, ref, name, value, actual)
    for ref, name, value in latest(truth, gt.WORKFLOW_TRANSITIONED):
        if name != "status":
            continue
        record = by_key.get(ref)
        actual = record.get("status") if record is not None else None
        check(_same(value, actual), gt.WORKFLOW_TRANSITIONED, ref, name, value, actual)
    for intent, event_type in (
        (gt.PSET_SET, "Pset.ValuesSet"),
        (gt.WORKFLOW_TRANSITIONED, "Workflow.Transitioned"),
    ):
        for item in {(i.ref, i.actor): i for i in truth if i.intent == intent}.values():
            record = by_key.get(item.ref)
            written_by(item, str(record["id"]) if record is not None else None, event_type)

    for item in truth:
        if item.intent == gt.SNAPSHOT_QUEUED:
            record = by_key.get(item.ref)
            written_by(item, str(record["id"]) if record is not None else None, QUEUED_EVENT)

    # --- links -------------------------------------------------------------------------------
    links_of: dict[str, list[dict[str, Any]]] = {}

    def active_link(source_key: str, relation: str, target_key: str) -> dict[str, Any] | None:
        source = by_key.get(source_key)
        if source is None:
            return None
        if source["id"] not in links_of:
            links_of[source["id"]] = reader.links(source["id"])
        return next(
            (
                v
                for v in links_of[source["id"]]
                if v["direction"] == "out"
                and v["relation"] == relation
                and v["other_key"] == target_key
                and v["status"] == "active"
            ),
            None,
        )

    for item in truth:
        if item.intent != gt.LINK_ADDED:
            continue
        found = active_link(item.expect["from"], item.expect["relation"], item.expect["to"])
        check(found is not None, item.intent, item.ref, "active link", True, found is not None)
        written_by(item, str(found["link_id"]) if found is not None else None, "Link.Added")

    # --- posts and proposals: each intended one needs its own match ------------------------------
    live = Counter((p["actor"], p["body"]) for p in reader.posts() if not p.get("retracted"))
    for item in truth:
        if item.intent != gt.POST_CREATED:
            continue
        want = (item.expect["author"], item.expect["body"])
        have = live[want] > 0
        if have:
            live[want] -= 1
        check(have, item.intent, item.ref, "post", item.expect["body"], None if not have else "ok")
        made = posted[(item.actor, item.expect["body"])] > 0
        if made:
            posted[(item.actor, item.expect["body"])] -= 1
        check(made, "actor_mismatch", item.ref, "post.created by", item.actor, None)
    queue = Counter((p["agent"], p["tool"]) for p in reader.proposals())
    for item in truth:
        if item.intent != gt.PROPOSAL_CREATED:
            continue
        want = (item.expect["agent"], item.expect["tool"])
        have = queue[want] > 0
        if have:
            queue[want] -= 1
        check(
            have, item.intent, item.ref, "proposal", item.expect["tool"], None if not have else "ok"
        )
        by = (item.actor, item.expect["agent"], item.expect["tool"])
        made = proposed[by] > 0
        if made:
            proposed[by] -= 1
        check(made, "actor_mismatch", item.ref, "proposal.created by", item.actor, None)

    # --- decisions on proposals: made by the person the log names, and (for a link) done --------
    decided: Counter[tuple[str, str, str, str]] = Counter(
        (str(p["status"]), str(p["agent"]), str(p["tool"]), str(p.get("decided_by")))
        for p in reader.proposals()
    )
    for item in truth:
        if item.intent not in (gt.PROPOSAL_ACCEPTED, gt.PROPOSAL_REJECTED):
            continue
        status = "accepted" if item.intent == gt.PROPOSAL_ACCEPTED else "rejected"
        key = (status, item.expect["agent"], item.expect["tool"], item.actor)
        have = decided[key] > 0
        if have:
            decided[key] -= 1
        check(have, item.intent, item.ref, f"proposal {status} by", item.actor, None)
        if status == "accepted" and "from" in item.expect:
            found = active_link(item.expect["from"], item.expect["relation"], item.expect["to"])
            check(found is not None, item.intent, item.ref, "link made", True, found is not None)
            written_by(item, str(found["link_id"]) if found is not None else None, "Link.Added")

    # --- a rejected link proposal made no link; an enabled actor that did nothing is silent -------
    allowed_links = {
        (i.expect["from"], i.expect["relation"], i.expect["to"])
        for i in truth
        if i.intent in (gt.PROPOSAL_ACCEPTED, gt.LINK_ADDED) and "from" in i.expect
    }
    for item in truth:
        if item.intent != gt.PROPOSAL_REJECTED or "from" not in item.expect:
            continue
        triple = (item.expect["from"], item.expect["relation"], item.expect["to"])
        made = triple not in allowed_links and active_link(*triple) is not None
        check(
            not made,
            "rejected_link_made",
            item.ref,
            "no link",
            None,
            "an active link" if made else None,
        )
    made_any = any(i.intent == gt.PROPOSAL_CREATED for i in truth)
    decided_any = any(i.intent in (gt.PROPOSAL_ACCEPTED, gt.PROPOSAL_REJECTED) for i in truth)
    if expected.days_played >= 1 and expected.proposals and not made_any:
        fail("actor_silent", "agent:sim-assistant", "proposal.created", "at least one", 0)
    if expected.days_played >= 1 and expected.decisions and made_any and not decided_any:
        fail("actor_silent", "user:sim-approver", "proposal decisions", "at least one", 0)

    # --- events: only the simulator wrote, and on a simulated day --------------------------------
    for event in events:
        source = str(event["source"])
        ref = f"seq {event.get('seq')} {event['event_type']}"
        if str(event["actor"]) in expected.operators and operator_event(event):
            report.excused += 1  # setup of a schedule by hand or by its worker: not a check
            continue
        scanner = event["event_type"] == "File.Processed" and event["actor"] == SCANNER
        if event["event_type"] in FILE_EVENTS:
            report.checked += 1
            record = record_of(event)
            if record not in intended:
                fail("event_stream", ref, "record", "a record the log names", record or None)
        if source == f"sim:{run_id}":
            report.checked += 1
            when = date.fromisoformat(str(event["effective_at"])[:10])
            if when not in played:
                fail("event_time", ref, "effective_at", "a played day", event["effective_at"])
        else:
            report.checked += 1
            decision = event["event_type"] in DECISION_EVENTS | FILE_EVENTS  # API, CLI or routes
            if not (source.startswith("mcp:") or decision):
                fail("event_source", ref, "source", f"sim:{run_id}", source)
        if source != f"sim:{run_id}" and event["event_type"] != "Proposal.Created":
            # An accepted proposal's effect and the decision, made through the API, carry
            # simulated time and must fall on a played day. Real time (effective_at equal to
            # recorded_at: a person deciding at the CLI) is exempt, as is the agent's own
            # Proposal.Created, which is made over MCP and stamped with real time.
            if event["effective_at"] != event["recorded_at"]:
                report.checked += 1
                when = date.fromisoformat(str(event["effective_at"])[:10])
                if when not in played:
                    fail("event_time", ref, "effective_at", "a played day", event["effective_at"])
        report.checked += 1
        if not (str(event["actor"]).startswith(SIM_ACTORS) or scanner):
            fail("event_actor", ref, "actor", "user:sim-* or agent:sim-*", event["actor"])
        if str(event["actor"]).startswith("agent:") and event["event_type"] not in AGENT_EVENTS:
            report.checked += 1
            fail("agent_wrote", ref, "event_type", sorted(AGENT_EVENTS), event["event_type"])
    if report.checked == 0:  # fail closed
        report.failures.append(Failure("nothing_checked", "-", "checks", "at least one", 0))
    return report
