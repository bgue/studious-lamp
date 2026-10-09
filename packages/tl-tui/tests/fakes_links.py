"""Link and workflow behaviour of `FakeClient` (P0-I3), kept apart so `fakes.py` stays readable.

The fake keeps links as plain dicts shaped like `cur_links` rows and follows the real rules where
they are cheap: it uses the real relation vocabulary, `next_status` for the lifecycle, and the same
error types. It simplifies the rest: expected links apply to every record (see `expected`), the
workflow is `FAKE_WORKFLOW` (states of the valve example), only the `expected_links` and `roles`
guards are evaluated (the others pass), and key detection uses `key_patterns`.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Protocol

from tl_core.ledger import ConcurrencyError
from tl_core.links.expected import ExpectedLink, MissingLink
from tl_core.links.lifecycle import next_status
from tl_core.links.provider import get_vocabulary
from tl_core.links.vocabulary import default_relation
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.detect import KeyChip, KeyMatch
from tl_core.services.commands import CommandResult
from tl_core.services.errors import (
    DuplicateLinkError,
    GuardFailedError,
    LinkNotFoundError,
    RecordNotFoundError,
    SelfLinkError,
    SuggestionDeclinedError,
    UnknownTransitionError,
)
from tl_core.services.link_queries import LinkCounts, LinkTarget, LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
    _OnLink,  # pyright: ignore[reportPrivateUsage]
)
from tl_core.services.workflow import (
    TransitionOption,
    TransitionWorkflow,
    WorkflowStatus,
)
from tl_core.workflow.definition import WorkflowDefinition
from tl_core.workflow.engine import GuardResult
from tl_tui.client import RelationInfo

FAKE_WORKFLOW = WorkflowDefinition.model_validate(
    {
        "id": "fake.valves",
        "version": 1,
        "record_type": "core.Record",
        "initial_state": "Design",
        "states": [{"name": "Design"}, {"name": "Installed"}, {"name": "Commissioned"}],
        "transitions": [
            {
                "name": "install",
                "label": "Install",
                "from": ["Design"],
                "to": "Installed",
                "guards": [{"kind": "expected_links"}, {"kind": "roles", "any_of": ["engineer"]}],
            },
            {
                "name": "commission",
                "label": "Commission",
                "from": ["Installed"],
                "to": "Commissioned",
            },
            {"name": "revert", "label": "Back to design", "from": ["Installed"], "to": "Design"},
        ],
    }
)
KEY_PATTERN = NumberingPattern(
    id="fake.fv",
    record_type="core.Record",
    template="FV-{seq:4}",
    type_code="FV",
    scope="project:*",
)


class _Host(Protocol):
    scope: str
    calls: list[str]
    _records: dict[str, dict[str, Any]]

    def _next_event(
        self, record: dict[str, Any], event_type: str, payload: dict[str, Any], actor: str
    ) -> Any: ...


class FakeLinkSupport:
    """Mixin for `FakeClient`: call `_init_links()` from its `__init__`."""

    def _init_links(self) -> None:
        self._links: dict[str, dict[str, Any]] = {}
        self._link_n = 0
        self._entered: dict[str, str] = {}
        # Expected links, applied to every record: a data sheet is expected by Installed.
        self.expected: list[ExpectedLink] = [
            ExpectedLink(relation="references", by_state="Installed", label="data sheet")
        ]
        self.workflow = FAKE_WORKFLOW
        self.key_patterns: list[NumberingPattern] = [KEY_PATTERN]
        self.link_commands: list[Any] = []

    # --- helpers ----------------------------------------------------

    def _host(self) -> _Host:
        return self  # type: ignore[return-value]

    def seed_link(
        self,
        from_key: str,
        to_key: str,
        relation: str = "references",
        *,
        status: str = "active",
        pin: str | None = None,
        note: str | None = None,
    ) -> str:
        """Add a link between two seeded records without going through a command."""
        host = self._host()
        by_key = {r["key"]: r for r in host._records.values()}
        self._link_n += 1
        link_id = f"LNK{self._link_n:023d}"
        self._links[link_id] = {
            "link_id": link_id,
            "scope": by_key[from_key]["scope"],
            "from_id": by_key[from_key]["id"],
            "to_id": by_key[to_key]["id"],
            "relation": relation,
            "status": status,
            "pin": pin,
            "note": note,
            "source": "manual",
            "confidence": 0.82 if status == "suggested" else None,
            "reason": None,
            "declined": False,
            "verified_by": None,
            "verified_at": None,
            "created_at": f"2026-10-09T10:{self._link_n:02d}:00+00:00",
            "version": 1,
        }
        return link_id

    def _record(self, record_id: str) -> dict[str, Any]:
        record = self._host()._records.get(record_id)
        if record is None:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return record

    def _result(self, link_id: str, version: int) -> CommandResult:
        return CommandResult(stream_id=link_id, key=None, version=version, events=[])

    # --- reads ------------------------------------------------------

    def links_of(self, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
        self._host().calls.append("links_of")
        self._record(record_id)
        vocabulary = get_vocabulary()
        order = {code: i for i, code in enumerate(vocabulary.codes())}
        views: list[LinkView] = []
        for row in self._links.values():
            if record_id not in (row["from_id"], row["to_id"]):
                continue
            if row["status"] == "retracted" and not include_retracted:
                continue
            direction = "out" if row["from_id"] == record_id else "in"
            other = self._record(row["to_id"] if direction == "out" else row["from_id"])
            views.append(
                LinkView(
                    link_id=row["link_id"],
                    direction=direction,
                    relation=row["relation"],
                    label=vocabulary.label(row["relation"], direction),
                    other_id=other["id"],
                    other_key=other["key"],
                    other_title=other["title"],
                    other_type=other["type"],
                    other_status=other["status"],
                    other_voided=other["voided"],
                    status=row["status"],
                    pin=row["pin"],
                    note=row["note"],
                    source=row["source"],
                    confidence=row["confidence"],
                    reason=row["reason"],
                    declined=row["declined"],
                    verified_by=row["verified_by"],
                    verified_at=row["verified_at"],
                    created_at=row["created_at"],
                    version=row["version"],
                )
            )
        views.sort(
            key=lambda v: (
                v.direction != "out",
                order.get(v.relation, len(order)),
                v.other_key or "",
                v.link_id,
            )
        )
        return views

    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
        self._host().calls.append("link_counts")
        found = {rid: LinkCounts(record_id=rid) for rid in record_ids}
        for row in self._links.values():
            for rid in (row["from_id"], row["to_id"]):
                if rid not in found:
                    continue
                counts = found[rid]
                status = row["status"]
                if status == "active" and rid == row["from_id"]:
                    counts.active_out += 1
                elif status == "active":
                    counts.active_in += 1
                elif status in ("stale", "broken", "suggested"):
                    setattr(counts, status, getattr(counts, status) + 1)
        return found

    def _unmet(self, record_id: str, expectations: Sequence[ExpectedLink]) -> list[MissingLink]:
        missing: list[MissingLink] = []
        for want in expectations:
            found = sum(
                1
                for row in self._links.values()
                if row["status"] == "active"
                and row["relation"] == want.relation
                and (
                    (want.direction in ("out", "either") and row["from_id"] == record_id)
                    or (want.direction in ("in", "either") and row["to_id"] == record_id)
                )
            )
            if found < want.min_count:
                missing.append(MissingLink(expectation=want, found=found, needed=want.min_count))
        return missing

    def expected_links(self, record_id: str) -> list[MissingLink]:
        self._host().calls.append("expected_links")
        self._record(record_id)
        return self._unmet(record_id, self.expected)

    def search_linkable(
        self,
        scope: str,
        query: str,
        *,
        record_type: str | None = None,
        exclude_id: str | None = None,
        limit: int = 20,
    ) -> list[LinkTarget]:
        self._host().calls.append("search_linkable")
        words = [w.lower() for w in query.split()]
        rows = [
            r
            for r in self._host()._records.values()
            if r["scope"] in (scope, "company")
            and not r["voided"]
            and (record_type is None or r["type"] == record_type)
            and r["id"] != exclude_id
            and all(w in f"{r['key'] or ''} {r['title']}".lower() for w in words)
        ]
        first = words[0] if words else ""
        rows.sort(key=lambda r: (not (r["key"] or "").lower().startswith(first), r["key"] or ""))
        counts = self.link_counts([r["id"] for r in rows])
        self._host().calls.pop()  # link_counts above is internal
        return [
            LinkTarget(
                id=r["id"],
                key=r["key"],
                type=r["type"],
                title=r["title"],
                status=r["status"],
                scope=r["scope"],
                link_total=counts[r["id"]].active,
            )
            for r in rows[:limit]
        ]

    def trace(
        self, record_id: str, *, depth: int = 2, direction: TraceDirection = "both"
    ) -> TraceNode:
        self._host().calls.append("trace")
        root_record = self._record(record_id)
        vocabulary = get_vocabulary()

        def node(
            rec: dict[str, Any], level: int, row: dict[str, Any] | None, way: Any
        ) -> TraceNode:
            return TraceNode(
                record_id=rec["id"],
                key=rec["key"],
                title=rec["title"],
                type=rec["type"],
                status=rec["status"],
                voided=rec["voided"],
                depth=level,
                link_id=None if row is None else row["link_id"],
                link_status=None if row is None else row["status"],
                relation=None if row is None else row["relation"],
                direction=way,
                label=None if row is None else vocabulary.label(row["relation"], way),
            )

        def neighbours(rid: str) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
            found = []
            for row in self._links.values():
                if row["status"] not in ("active", "stale", "broken"):
                    continue
                if row["from_id"] == rid and direction in ("out", "both"):
                    found.append((row, "out", self._record(row["to_id"])))
                elif row["to_id"] == rid and direction in ("in", "both"):
                    found.append((row, "in", self._record(row["from_id"])))
            found.sort(key=lambda t: (t[1] != "out", t[0]["relation"], t[2]["key"] or ""))
            return found

        root = node(root_record, 0, None, None)
        seen = {root_record["id"]: root}
        frontier = [root]
        for level in range(1, depth + 1):
            following = []
            for parent in frontier:
                for row, way, other in neighbours(parent.record_id):
                    if other["id"] in seen:
                        continue
                    child = node(other, level, row, way)
                    parent.children.append(child)
                    seen[other["id"]] = child
                    following.append(child)
            frontier = following
        for tree_node in seen.values():
            tree_node.more = len(
                {o["id"] for _, _, o in neighbours(tree_node.record_id)} - set(seen)
            )
        return root

    def detect_keys(self, scope: str, text: str, *, linked_to: str | None = None) -> list[KeyChip]:
        self._host().calls.append("detect_keys")
        chips: list[KeyChip] = []
        for pattern in self.key_patterns:
            compiled = pattern.compiled()
            for found in compiled.search_regex().finditer(text):
                if compiled.parse(found.group(0)) is None:
                    continue
                match = KeyMatch(
                    start=found.start(), end=found.end(), key=found.group(0), pattern_id=pattern.id
                )
                record = next(
                    (
                        r
                        for r in self._host()._records.values()
                        if r["key"] == match.key and r["scope"] in (scope, "company")
                    ),
                    None,
                )
                if record is not None and record["id"] == linked_to:
                    continue
                status = None
                if record is not None and linked_to is not None:
                    live = [
                        r["status"]
                        for r in self._links.values()
                        if r["status"] != "retracted"
                        and {r["from_id"], r["to_id"]} == {linked_to, record["id"]}
                    ]
                    status = live[0] if live else None
                chips.append(
                    KeyChip(
                        start=match.start,
                        end=match.end,
                        key=match.key,
                        pattern_id=match.pattern_id,
                        record_id=None if record is None else record["id"],
                        record_type=None if record is None else record["type"],
                        title=None if record is None else record["title"],
                        status=None if record is None else record["status"],
                        voided=False if record is None else record["voided"],
                        link_status=status,
                    )
                )
        return sorted(chips, key=lambda c: c.start)

    def relations(self) -> list[RelationInfo]:
        self._host().calls.append("relations")
        vocabulary = get_vocabulary()
        return [
            RelationInfo(
                code=r.code,
                label=r.label,
                inverse_code=r.inverse_code,
                inverse_label=r.inverse_label,
            )
            for r in (vocabulary.get(c) for c in vocabulary.codes())
        ]

    def default_relation(self, from_type: str, to_type: str) -> str:
        self._host().calls.append("default_relation")
        return default_relation(from_type, to_type)

    # --- link commands ----------------------------------------------

    def _create(self, cmd: AddLink, status: str) -> CommandResult:
        self.link_commands.append(cmd)
        source = self._record(cmd.from_id)
        target = self._record(cmd.to_id)
        if cmd.from_id == cmd.to_id:
            raise SelfLinkError("a record cannot be linked to itself")
        relation = cmd.relation or default_relation(source["type"], target["type"])
        get_vocabulary().get(relation)
        for row in self._links.values():
            same = (row["from_id"], row["to_id"], row["relation"]) == (
                cmd.from_id,
                cmd.to_id,
                relation,
            )
            if same and status == "suggested" and row["declined"]:
                raise SuggestionDeclinedError("this suggestion was declined before")
            if same and row["status"] != "retracted":
                raise DuplicateLinkError(f"a {relation} link already exists ({row['status']})")
        self._link_n += 1
        link_id = f"LNK{self._link_n:023d}"
        self._links[link_id] = {
            "link_id": link_id,
            "scope": cmd.scope,
            "from_id": cmd.from_id,
            "to_id": cmd.to_id,
            "relation": relation,
            "status": status,
            "pin": cmd.pin,
            "note": cmd.note,
            "source": cmd.link_source,
            "confidence": getattr(cmd, "confidence", None),
            "reason": None,
            "declined": False,
            "verified_by": None,
            "verified_at": None,
            "created_at": f"2026-10-09T10:{self._link_n:02d}:00+00:00",
            "version": 1,
        }
        return self._result(link_id, 1)

    def add_link(self, cmd: AddLink) -> CommandResult:
        self._host().calls.append("add_link")
        return self._create(cmd, "active")

    def suggest_link(self, cmd: SuggestLink) -> CommandResult:
        self._host().calls.append("suggest_link")
        return self._create(cmd, "suggested")

    def _act(
        self, cmd: _OnLink, event_type: str, changes: dict[str, Any], flag: str | None = None
    ) -> CommandResult:
        self.link_commands.append(cmd)
        row = self._links.get(cmd.link_id)
        if row is None:
            raise LinkNotFoundError(f"no link {cmd.link_id!r}")
        if cmd.expected_version is not None and cmd.expected_version != row["version"]:
            raise ConcurrencyError(
                f"expected version {cmd.expected_version}, found {row['version']}"
            )
        row["status"] = next_status(row["status"], event_type, flag=flag)
        row.update(changes)
        row["version"] += 1
        return self._result(cmd.link_id, row["version"])

    def accept_link(self, cmd: AcceptLink) -> CommandResult:
        self._host().calls.append("accept_link")
        return self._act(cmd, "Link.Accepted", {} if cmd.note is None else {"note": cmd.note})

    def decline_link(self, cmd: DeclineLink) -> CommandResult:
        self._host().calls.append("decline_link")
        return self._act(cmd, "Link.Declined", {"declined": True, "reason": cmd.reason})

    def repin_link(self, cmd: RepinLink) -> CommandResult:
        self._host().calls.append("repin_link")
        return self._act(cmd, "Link.Repinned", {"pin": cmd.pin})

    def verify_link(self, cmd: VerifyLink) -> CommandResult:
        self._host().calls.append("verify_link")
        return self._act(
            cmd,
            "Link.Verified",
            {"verified_by": cmd.actor, "verified_at": "2026-10-09T11:00:00+00:00"},
        )

    def flag_link(self, cmd: FlagLink) -> CommandResult:
        self._host().calls.append("flag_link")
        return self._act(cmd, "Link.Flagged", {"reason": cmd.reason}, flag=cmd.status)

    def retract_link(self, cmd: RetractLink) -> CommandResult:
        self._host().calls.append("retract_link")
        return self._act(cmd, "Link.Retracted", {"reason": cmd.reason})

    # --- workflow ---------------------------------------------------

    def _guards(
        self, record: dict[str, Any], to_state: str, guards: Sequence[Any], roles: Sequence[str]
    ) -> list[GuardResult]:
        results: list[GuardResult] = []
        for guard in guards:
            if guard.kind == "expected_links":
                wanted = [e for e in self.expected if e.by_state == to_state]
                unmet = self._unmet(record["id"], wanted)
                parts = [f"{m.expectation.display} ({m.found} of {m.needed})" for m in unmet]
                results.append(
                    GuardResult(
                        kind="expected_links",
                        passed=not unmet,
                        message="missing links: " + "; ".join(parts)
                        if unmet
                        else "required links are present",
                        details={"missing": [m.model_dump() for m in unmet]},
                    )
                )
            elif guard.kind == "roles":
                held = sorted(set(roles) & set(guard.any_of))
                results.append(
                    GuardResult(
                        kind="roles",
                        passed=bool(held),
                        message=f"role {held[0]} held"
                        if held
                        else f"needs one of the roles: {', '.join(guard.any_of)}",
                    )
                )
            else:
                results.append(GuardResult(kind=guard.kind, passed=True, message="ok (fake)"))
        return results

    def workflow_status(self, record_id: str, *, roles: Sequence[str] = ()) -> WorkflowStatus:
        self._host().calls.append("workflow_status")
        record = self._record(record_id)
        state = record["status"] or self.workflow.initial_state
        options = []
        for transition in self.workflow.transitions_from(state):
            guards = self._guards(record, transition.to, transition.guards, roles)
            options.append(
                TransitionOption(
                    transition=transition.name,
                    label=transition.label or transition.name,
                    from_state=state,
                    to_state=transition.to,
                    allowed=all(g.passed for g in guards),
                    guards=guards,
                )
            )
        return WorkflowStatus(
            record_id=record_id,
            key=record["key"],
            workflow=self.workflow.id,
            workflow_version=self.workflow.version,
            state=state,
            state_label=state,
            entered_at=self._entered.get(record_id) or str(record["created_at"]),
            version=record["version"],
            options=options,
        )

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        self._host().calls.append("transition")
        self.link_commands.append(cmd)
        record = self._record(cmd.stream_id)
        if record["version"] != cmd.expected_version:
            raise ConcurrencyError(
                f"expected version {cmd.expected_version}, found {record['version']}"
            )
        state = record["status"] or self.workflow.initial_state
        transition = self.workflow.transition(cmd.transition)
        if transition is None or state not in transition.from_states:
            raise UnknownTransitionError(f"transition {cmd.transition!r} cannot start in {state!r}")
        results = self._guards(record, transition.to, transition.guards, cmd.actor_roles)
        failed = [r for r in results if not r.passed]
        if failed:
            raise GuardFailedError(
                f"cannot {cmd.transition} {record['key']}: " + "; ".join(r.message for r in failed),
                list(results),
            )
        record["status"] = transition.to
        event = self._host()._next_event(
            record,
            "Workflow.Transitioned",
            {
                "workflow": self.workflow.id,
                "workflow_version": self.workflow.version,
                "from_state": state,
                "to_state": transition.to,
                "transition": transition.name,
            },
            cmd.actor,
        )
        self._entered[record["id"]] = record["updated_at"]
        return CommandResult(
            stream_id=record["id"], key=record["key"], version=record["version"], events=[event]
        )


__all__ = ["FAKE_WORKFLOW", "FakeLinkSupport", "KEY_PATTERN", "deepcopy"]
