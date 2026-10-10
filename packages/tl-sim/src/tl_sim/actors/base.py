"""The deterministic actor base and the ``Recorder`` that keeps the ground truth honest.

An actor decides what to do from the day's random generator and from what it reads through
``ctx.client``; it never calls anything else. Every write goes through a ``Recorder`` method,
which makes the call and writes the matching ``GroundTruth`` line in the same breath, so the log
can never claim something the actor did not try or miss something it did. Reads
(``Recorder.records``) are not recorded.

An actor that is refused by the suite (a failed workflow guard, a transition from the wrong state)
is playing a realistic day: ``Recorder.transition`` returns ``False`` and records nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_core.services.errors import GuardFailedError, InvalidStateError, UnknownTransitionError

from tl_sim import groundtruth as gt
from tl_sim.types import GroundTruth, SimContext

RECORD_TYPE = "core.Record"
INITIAL_STATE = "Draft"  # the state of a record whose status is empty (schema/fixtures/workflows)
REFUSALS = (GuardFailedError, InvalidStateError, UnknownTransitionError)
MAX_RECORDS = 5000  # the API's page limit; a Phase 0 simulation stays far below it


@dataclass(frozen=True)
class Rec:
    """The part of a record an actor needs: ids to write with, the key to talk about."""

    id: str
    key: str
    title: str
    status: str | None = None

    @property
    def state(self) -> str:
        """The workflow state: an empty ``status`` means the initial state."""
        return self.status or INITIAL_STATE

    @classmethod
    def of(cls, envelope: dict[str, Any]) -> Rec:
        return cls(
            id=str(envelope["id"]),
            key=str(envelope["key"]),
            title=str(envelope["title"]),
            status=envelope.get("status"),
        )


class Recorder:
    """Writes through ``ctx.client`` and appends one ``GroundTruth`` per successful write."""

    def __init__(self, ctx: SimContext, identity: str) -> None:
        self.ctx = ctx
        self.identity = identity
        self.truth: list[GroundTruth] = []
        self._posts = 0
        self._proposals = 0

    def _stamp(self) -> str:
        """The step's start to the minute: one actor acts once per slot, so this is unique."""
        return self.ctx.now.strftime("%Y-%m-%dT%H:%M")

    def _note(self, intent: str, ref: str, expect: dict[str, Any]) -> None:
        self.truth.append(
            GroundTruth(at=self.ctx.now, actor=self.identity, intent=intent, ref=ref, expect=expect)
        )

    # --- reads (not recorded) ------------------------------------------------------------

    def records(self, q: str = "", *, title_prefix: str | None = None) -> list[Rec]:
        """Records matching ``q`` in key order; ``title_prefix`` keeps titles starting with it."""
        found = self.ctx.client.query(q, limit=MAX_RECORDS)
        recs = [Rec.of(e) for e in found if not e.get("voided")]
        if title_prefix is not None:
            recs = [r for r in recs if r.title.startswith(title_prefix)]
        return sorted(recs, key=lambda r: r.key)

    # --- writes (each one is a line of ground truth) --------------------------------------

    def create(self, title: str) -> Rec:
        made = self.ctx.client.create_record(record_type=RECORD_TYPE, title=title)
        rec = Rec(id=str(made["id"]), key=str(made["key"]), title=title)
        self._note(
            gt.RECORD_CREATED,
            rec.key,
            {"title": title, "record_type": RECORD_TYPE, "voided": False},
        )
        return rec

    def set_psets(self, rec: Rec, values: dict[str, dict[str, Any]]) -> None:
        """``values`` is ``{pset: {property: value}}``, e.g. ``{"valve_data": {"size_in": 6}}``."""
        self.ctx.client.set_psets(rec.id, values)
        for pset in sorted(values):
            for prop in sorted(values[pset]):
                self._note(gt.PSET_SET, rec.key, {f"psets.{pset}.{prop}": values[pset][prop]})

    def link(self, source: Rec, target: Rec, relation: str) -> None:
        self.ctx.client.link(source.id, target.id, relation)
        self._note(
            gt.LINK_ADDED,
            f"{source.key} {relation} {target.key}",
            {"from": source.key, "to": target.key, "relation": relation},
        )

    def transition(self, rec: Rec, transition: str, to_state: str) -> bool:
        """Run ``transition``, expecting ``to_state``. ``False`` when the suite refused it."""
        try:
            self.ctx.client.transition(rec.id, transition)
        except REFUSALS:
            return False
        self._note(
            gt.WORKFLOW_TRANSITIONED, rec.key, {"status": to_state, "transition": transition}
        )
        return True

    def post(self, body: str) -> str:
        """Post to the project feed. Returns the ground-truth name of the post."""
        self.ctx.client.post(body)
        self._posts += 1
        ref = f"post:{self.identity}:{self._stamp()}:{self._posts}"
        self._note(gt.POST_CREATED, ref, {"body": body, "author": self.identity})
        return ref

    def propose(self, tool: str, arguments: dict[str, Any]) -> str:
        """Ask the review queue (MCP, propose-only). Returns the ground-truth name."""
        self.ctx.client.propose(tool, arguments)
        self._proposals += 1
        ref = f"proposal:{self.identity}:{self._stamp()}:{self._proposals}"
        self._note(gt.PROPOSAL_CREATED, ref, {"tool": tool, "agent": self.identity})
        return ref


class BaseActor:
    """Subclasses set ``name`` and implement ``act``; ``step`` is the ``Actor`` protocol."""

    name: str = ""

    def __init__(self, params: Any) -> None:
        self.params = params
        self.identity: str = f"agent:sim-{self.name}"

    def step(self, ctx: SimContext) -> list[GroundTruth]:
        recorder = Recorder(ctx, self.identity)
        self.act(ctx, recorder)
        return recorder.truth

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError
