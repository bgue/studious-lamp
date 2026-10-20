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

from tl_core.services.errors import (
    DuplicateLinkError,
    GuardFailedError,
    InvalidStateError,
    UnknownTransitionError,
)
from tl_mod_correspondence.errors import ItemStateError

from tl_sim import groundtruth as gt
from tl_sim.client import (
    DocumentDesk,
    ProposalDesk,
    ProposeUnavailableError,
    ScheduleDesk,
    TagDesk,
    TechnicalDesk,
)
from tl_sim.mcp_caller import ProposalRefusedError
from tl_sim.types import GroundTruth, SimContext

RECORD_TYPE = "core.Record"
INITIAL_STATE = "Draft"  # the state of a record whose status is empty (schema/fixtures/workflows)
REFUSALS = (GuardFailedError, InvalidStateError, UnknownTransitionError)
TAG_TYPE = "engineering.Tag"
DOCUMENT_TYPE = "documents.Document"
REVISION_TYPE = "documents.Revision"
SCHEDULE_SNAPSHOT_TYPE = "schedule.ScheduleSnapshot"
ACTIVITY_REF_TYPE = "schedule.ActivityRef"
TECHNICAL_TYPE = "correspondence.TechnicalItem"
ACTIVITY_RELATION = "references"  # what links a record to an activity (ADR-0015 section 5)
MAX_REF_TITLE = 200  # the module cuts the title of an activity's reference here
SUPERSEDED = "Superseded"  # the state of a tag that a rename replaced
MAX_RECORDS = 5000  # the API's page limit; a Phase 0 simulation stays far below it


def plural(count: int, one: str, many: str | None = None) -> str:
    """``1 valve``, ``2 valves``, ``0 valves``: the count and the right form of the noun."""
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _tag_expect(title: str) -> dict[str, Any]:
    return {"title": title, "record_type": TAG_TYPE, "voided": False}


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


@dataclass(frozen=True)
class Sched:
    """A schedule as a person sees it in the list: the code names it, the id is for writing."""

    id: str
    code: str
    title: str
    current: int | None  # the number of the published snapshot, if there is one
    snapshots: int  # how many snapshots there are, whatever their state

    @classmethod
    def of(cls, view: dict[str, Any]) -> Sched:
        number = view.get("current_snapshot_number")
        return cls(
            id=str(view["id"]),
            code=str(view["code"]),
            title=str(view["title"]),
            current=None if number is None else int(number),
            snapshots=int(view["snapshot_count"]),
        )


@dataclass(frozen=True)
class Activity:
    """An activity of the current snapshot: the P6 id the link names, and its name."""

    id: str
    name: str


@dataclass(frozen=True)
class Rfi:
    """An RFI as the log shows it: the id to write with, the number to talk about."""

    id: str
    number: str
    subject: str
    state: str

    @classmethod
    def of(cls, line: dict[str, Any]) -> Rfi:
        return cls(
            id=str(line["id"]),
            number=str(line["number"]),
            subject=str(line["subject"]),
            state=str(line["state"]),
        )


class Recorder:
    """Writes through ``ctx.client`` and appends one ``GroundTruth`` per successful write."""

    def __init__(self, ctx: SimContext, identity: str) -> None:
        self.ctx = ctx
        self.identity = identity
        self.truth: list[GroundTruth] = []
        self._posts = 0
        self._proposals = 0
        self._decisions = 0

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

    def _tag_desk(self) -> TagDesk:
        client = self.ctx.client
        if not isinstance(client, TagDesk):
            raise ProposeUnavailableError("this client cannot keep the tag list")
        return client

    def create_tag(self, number: str, class_code: str, service: str) -> Rec:
        """Register a tag; the title of the record is the service description."""
        made = self._tag_desk().create_tag(number, class_code, service)
        rec = Rec(id=str(made["id"]), key=number, title=service)
        self._note(gt.RECORD_CREATED, rec.key, _tag_expect(service))
        return rec

    def rename_tag(self, old: Rec, new_number: str, reason: str) -> Rec:
        """Replace ``old`` by a tag numbered ``new_number``: three things the log names."""
        made = self._tag_desk().rename_tag(old.id, new_number, reason)
        new = Rec(id=str(made["id"]), key=new_number, title=old.title)
        self._note(gt.RECORD_CREATED, new.key, _tag_expect(old.title))
        self._note(
            gt.LINK_ADDED,
            f"{new.key} supersedes {old.key}",
            {"from": new.key, "to": old.key, "relation": "supersedes"},
        )
        self._note(
            gt.WORKFLOW_TRANSITIONED, old.key, {"status": SUPERSEDED, "transition": "supersede"}
        )
        return new

    def _document_desk(self) -> DocumentDesk:
        client = self.ctx.client
        if not isinstance(client, DocumentDesk):
            raise ProposeUnavailableError("this client cannot keep the document register")
        return client

    def register_document(self, number: str, title: str, doc_type: str, discipline: str) -> Rec:
        """Register a document; its key is its number."""
        made = self._document_desk().register_document(number, title, doc_type, discipline)
        rec = Rec(id=str(made["id"]), key=number, title=title)
        self._note(
            gt.RECORD_CREATED,
            rec.key,
            {"title": title, "record_type": DOCUMENT_TYPE, "voided": False},
        )
        return rec

    def start_revision(self, document: Rec, purpose: str) -> Rec:
        """Start the next revision of ``document``; its key is ``<number>@<code>``.

        The code is the registry's: the revision scheme of the document's type decides it (``A``
        for most types, ``0`` for a specification), so the key is read from the answer.
        """
        made = self._document_desk().start_revision(document.id, purpose)
        key = str(made["key"])
        title = f"{document.key} rev {key.rsplit('@', 1)[-1]}"
        rec = Rec(id=str(made["id"]), key=key, title=title)
        self._note(
            gt.RECORD_CREATED,
            rec.key,
            {"title": title, "record_type": REVISION_TYPE, "voided": False},
        )
        return rec

    def _technical_desk(self) -> TechnicalDesk:
        client = self.ctx.client
        if not isinstance(client, TechnicalDesk):
            raise ProposeUnavailableError("this client cannot keep the RFI log")
        return client

    def rfis(self, *, subject_prefix: str | None = None) -> list[Rfi]:
        """The project's RFIs in number order (a read, not recorded)."""
        found = [Rfi.of(line) for line in self._technical_desk().rfis()]
        if subject_prefix is not None:
            found = [x for x in found if x.subject.startswith(subject_prefix)]
        return sorted(found, key=lambda x: x.number)

    def raise_rfi(self, subject: str, question: str, discipline: str, required_by: str) -> Rfi:
        """Raise an RFI and send it to internal review: the log names the record. The state it
        ends in (Internal review) is not noted, because a controller moves it on (issues it)
        beside the run, and the log says only what no one else changes."""
        desk = self._technical_desk()
        made = desk.raise_rfi(subject, question, discipline, required_by)
        rfi = Rfi(id=str(made["id"]), number=str(made["key"]), subject=subject, state="Draft")
        self._note(
            gt.RECORD_CREATED,
            rfi.number,
            {"title": subject, "record_type": TECHNICAL_TYPE, "voided": False},
        )
        desk.submit_rfi(rfi.id)
        return rfi

    def answer_rfi(self, rfi: Rfi, answer: str, cost_impact: str, schedule_impact: str) -> bool:
        """Answer an RFI that waits for one: it ends in Answered. ``False`` (nothing recorded) when
        the suite refused (it was answered meanwhile)."""
        try:
            self._technical_desk().answer_rfi(rfi.id, answer, cost_impact, schedule_impact)
        except REFUSALS + (ItemStateError,):
            return False
        self._note(
            gt.WORKFLOW_TRANSITIONED, rfi.number, {"status": "Answered", "transition": "answer"}
        )
        return True

    def accept_answer(self, rfi: Rfi) -> bool:
        """Accept the answer of an RFI: it ends in Accepted."""
        try:
            self._technical_desk().accept_answer(rfi.id)
        except REFUSALS + (ItemStateError,):
            return False
        self._note(
            gt.WORKFLOW_TRANSITIONED, rfi.number, {"status": "Accepted", "transition": "accept"}
        )
        return True

    def _schedule_desk(self) -> ScheduleDesk:
        client = self.ctx.client
        if not isinstance(client, ScheduleDesk):
            raise ProposeUnavailableError("this client cannot send schedule updates")
        return client

    def schedules(self) -> list[Sched]:
        """The project's schedules in code order (a read, not recorded)."""
        found = [Sched.of(view) for view in self._schedule_desk().schedules()]
        return sorted(found, key=lambda sched: sched.code)

    def activities(self, sched: Sched, *, limit: int = 200) -> list[Activity]:
        """The first ``limit`` activities of the schedule's current snapshot, in P6 id order."""
        rows = self._schedule_desk().current_activities(sched.code, limit=limit)
        found = [Activity(id=str(row["activity_id"]), name=str(row["name"])) for row in rows]
        return sorted(found, key=lambda activity: activity.id)

    def send_update(self, sched: Sched, filename: str, data: bytes) -> Rec:
        """Open the next snapshot of ``sched``, attach the P6 export and queue its build.

        Two things the log names: the snapshot record (``<code>#<n>``, read from the answer as for a
        revision) and that its build was queued. A controller publishes it once a worker has built
        it; neither is this person's act.
        """
        desk = self._schedule_desk()
        opened = desk.open_snapshot(sched.id)
        key = str(opened["key"])
        title = f"{sched.title} snapshot {key.rsplit('#', 1)[-1]}"
        snapshot = Rec(id=str(opened["id"]), key=key, title=title)
        self._note(
            gt.RECORD_CREATED,
            snapshot.key,
            {"title": title, "record_type": SCHEDULE_SNAPSHOT_TYPE, "voided": False},
        )
        desk.attach_snapshot_file(snapshot.id, filename, data)
        desk.start_snapshot(snapshot.id)
        self._note(gt.SNAPSHOT_QUEUED, snapshot.key, {"file": filename})
        return snapshot

    def link_activity(self, record: Rec, sched: Sched, activity: Activity) -> bool:
        """Link ``record`` to an activity of the current snapshot by its P6 id.

        The first link to an activity makes the activity's reference record (``<code>/<id>``): the
        log names it, then the link. ``False`` (nothing recorded) when the record is already linked
        to that activity, which a realistic day shrugs off.
        """
        try:
            made = self._schedule_desk().link_activity(record.id, sched.id, activity.id)
        except DuplicateLinkError:
            return False
        ref = f"{sched.code}/{activity.id}"
        if made["ref_created"]:
            self._note(
                gt.RECORD_CREATED,
                ref,
                {
                    "title": f"{activity.id} {activity.name}"[:MAX_REF_TITLE],
                    "record_type": ACTIVITY_REF_TYPE,
                    "voided": False,
                },
            )
        self._note(
            gt.LINK_ADDED,
            f"{record.key} {ACTIVITY_RELATION} {ref}",
            {"from": record.key, "to": ref, "relation": ACTIVITY_RELATION},
        )
        return True

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

    def propose(self, tool: str, arguments: dict[str, Any]) -> str | None:
        """Ask the review queue (MCP, propose-only). Returns the ground-truth name.

        ``None`` (and no ground truth) only for the one refusal a realistic day shrugs off: a link
        that already exists. Any other refusal (budget, bad argument, permission, unknown record)
        is raised, so a broken run cannot pass by proposing nothing.
        """
        try:
            self.ctx.client.propose(tool, arguments)
        except ProposalRefusedError as exc:
            if exc.is_duplicate_link:
                return None
            raise
        self._proposals += 1
        ref = f"proposal:{self.identity}:{self._stamp()}:{self._proposals}"
        self._note(gt.PROPOSAL_CREATED, ref, {"tool": tool, "agent": self.identity})
        return ref

    # --- the review queue, worked by a person (needs a client with a ProposalDesk) --------------

    def _desk(self) -> ProposalDesk:
        client = self.ctx.client
        if not isinstance(client, ProposalDesk):
            raise ProposeUnavailableError("this client cannot work the review queue")
        return client

    def pending(self) -> list[dict[str, Any]]:
        """The pending proposals of the project, oldest first (``ProposalView`` as dicts)."""
        return self._desk().pending_proposals()

    def key_of(self, record_id: str) -> str:
        """The key of a record named by id (a proposal's command holds ids)."""
        found = self.ctx.client.query(f"id:{record_id}", limit=1)
        return str(found[0]["key"])

    def decide(self, proposal: dict[str, Any], *, accept: bool, reason: str = "") -> str | None:
        """Accept or reject ``proposal`` as this actor. Returns the ground-truth name.

        ``None`` (no ground truth) when an accepted proposal could no longer be applied: the suite
        marks it ``failed`` and nothing was done.
        """
        desk = self._desk()
        tool, agent = str(proposal["tool"]), str(proposal["agent"])
        self._decisions += 1
        ref = f"decision:{self.identity}:{self._stamp()}:{self._decisions}"
        expect: dict[str, Any] = {"tool": tool, "agent": agent}
        if tool == "link_records":  # what the proposal would make, so a rejection can be checked
            command = proposal["command"]
            expect["from"] = self.key_of(str(command["from_id"]))
            expect["to"] = self.key_of(str(command["to_id"]))
            expect["relation"] = command.get("relation")
        if not accept:
            desk.reject_proposal(str(proposal["proposal_id"]), reason)
            self._note(gt.PROPOSAL_REJECTED, ref, {**expect, "reason": reason})
            return ref
        decided = desk.accept_proposal(str(proposal["proposal_id"]))
        if decided.get("status") != "accepted":
            return None
        self._note(gt.PROPOSAL_ACCEPTED, ref, expect)
        return ref


class BaseActor:
    """Subclasses set ``name`` and implement ``act``; ``step`` is the ``Actor`` protocol."""

    name: str = ""

    def __init__(self, params: Any) -> None:
        self.params = params
        self.identity: str = f"user:sim-{self.name}"

    def step(self, ctx: SimContext) -> list[GroundTruth]:
        recorder = Recorder(ctx, self.identity)
        self.act(ctx, recorder)
        return recorder.truth

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError
