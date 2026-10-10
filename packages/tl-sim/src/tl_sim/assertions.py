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

Three more checks catch what the scenario did not intend: the scope holds no record the log does
not name, every event in the scope was written by the simulator (``source`` ``sim:<run>``, or an
MCP proposal by a simulated agent), and every simulator event carries a simulated time on a day
that was played (``effective_at``, FANOUT D5).
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

    def fail(check: str, ref: str, name: str, expected: Any, actual: Any) -> None:
        report.failures.append(Failure(check, ref, name, expected, actual))

    def check(ok: bool, check_name: str, ref: str, name: str, expected: Any, actual: Any) -> None:
        report.checked += 1
        if not ok:
            fail(check_name, ref, name, expected, actual)

    by_key = {str(r["key"]): r for r in reader.records()}

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

    # --- links -------------------------------------------------------------------------------
    links_of: dict[str, list[dict[str, Any]]] = {}
    for item in truth:
        if item.intent != gt.LINK_ADDED:
            continue
        source = by_key.get(item.expect["from"])
        found: dict[str, Any] | None = None
        if source is not None:
            if source["id"] not in links_of:
                links_of[source["id"]] = reader.links(source["id"])
            found = next(
                (
                    v
                    for v in links_of[source["id"]]
                    if v["direction"] == "out"
                    and v["relation"] == item.expect["relation"]
                    and v["other_key"] == item.expect["to"]
                    and v["status"] == "active"
                ),
                None,
            )
        check(found is not None, item.intent, item.ref, "active link", True, found is not None)

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

    # --- events: only the simulator wrote, and on a simulated day --------------------------------
    for event in reader.events():
        source = str(event["source"])
        ref = f"seq {event.get('seq')} {event['event_type']}"
        if source == f"sim:{run_id}":
            report.checked += 1
            when = date.fromisoformat(str(event["effective_at"])[:10])
            if when not in played:
                fail("event_time", ref, "effective_at", "a played day", event["effective_at"])
        else:
            report.checked += 1
            if not source.startswith("mcp:"):
                fail("event_source", ref, "source", f"sim:{run_id}", source)
    return report
