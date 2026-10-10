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
| ``proposal.created`` | a proposal by that agent for that tool exists (once per intended one) |
| ``proposal.accepted`` / ``rejected`` | that person decided such a proposal that way (a link too) |

Each of those is also checked against the ledger event that fulfilled it: the actor that wrote
that record, pset value, link, transition, post or proposal must be the actor the log names
(``actor_mismatch``). The check fails closed: an empty log, or a run that checked nothing, is a
failure, not a pass.

Three more checks catch what the scenario did not intend: the scope holds no record the log does
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
SIM_ACTORS = ("user:sim-", "agent:sim-")
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


@dataclass
class AssertionReport:
    checked: int = 0
    failures: list[Failure] = field(default_factory=list[Failure])
    counts: dict[str, int] = field(default_factory=dict[str, int])  # intents seen in the log

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
) -> AssertionReport:
    """Check every intent in ``truth`` against ``reader``; ``played`` holds the simulated dates."""
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
    writers: dict[tuple[str, str], set[str]] = {}  # (stream id, event type) -> actors
    posted: Counter[tuple[str, str]] = Counter()  # (actor, body) of Feed.Posted
    proposed: Counter[tuple[str, str, str]] = Counter()  # (actor, agent, tool) of Proposal.Created
    for event in events:
        writers.setdefault((str(event["stream_id"]), str(event["event_type"])), set()).add(
            str(event["actor"])
        )
        payload = event.get("payload") or {}
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

    # --- events: only the simulator wrote, and on a simulated day --------------------------------
    for event in events:
        source = str(event["source"])
        ref = f"seq {event.get('seq')} {event['event_type']}"
        if source == f"sim:{run_id}":
            report.checked += 1
            when = date.fromisoformat(str(event["effective_at"])[:10])
            if when not in played:
                fail("event_time", ref, "effective_at", "a played day", event["effective_at"])
        else:
            report.checked += 1
            decision = event["event_type"] in DECISION_EVENTS  # made over the API or the CLI
            if not (source.startswith("mcp:") or decision):
                fail("event_source", ref, "source", f"sim:{run_id}", source)
        report.checked += 1
        if not str(event["actor"]).startswith(SIM_ACTORS):
            fail("event_actor", ref, "actor", "user:sim-* or agent:sim-*", event["actor"])
    if report.checked == 0:  # fail closed
        report.failures.append(Failure("nothing_checked", "-", "checks", "at least one", 0))
    return report
