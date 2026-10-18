"""The rules worker (brief §18.8; FANOUT D7, D3, D11; ADR-0017).

A rule is *when* (a ``WebhookFilter`` on events) -> *if* (a query-language condition on the subject
record) -> *then* (``RuleStep`` commands). The worker follows the ledger off the write path, in
batches from the operational cursor ``rule_cursor``; a rule never blocks or fails a person's write.

**Exactly-once effect.** A row ``rule_firing`` is written in the same unit of work as the commands
a firing runs, and a firing is skipped when the row for the same rule and event exists. A crash
between the commands and the cursor re-reads the event and finds the row.

**Loop protection.** The depth of a chain is read from the triggering event's source: a rule stamps
what it does with ``rule:<key>@<version>/d<depth>``; any other source is depth 0. At
``RULE_MAX_CAUSATION_DEPTH`` the firing is ``depth_limit`` and runs nothing. A rule never fires on
an event whose source names the same rule (``self_trigger``).

**Budgets.** At most ``RULE_MAX_RULES_PER_EVENT`` matched rules per event (in key order) and
``RULE_MAX_COMMANDS_PER_EVENT`` commands per event; the excess is ``budget``.

**Service actor.** Every command runs as the rule's ``svc:rule-<key>`` with its declared access,
through ``automation.plan_command`` (the allow-list, the access, the model) and the handler's own
guards. A rule in ``propose`` mode makes one proposal per command; accepting is a person's.

**Kill switch.** Read inside every firing. When on, the event is recorded as ``killed`` for each
rule it matches and is not replayed later.

A refused, depth-limited or over-budget firing is a ledger event on the rule's stream
(``Rule.Blocked``) so its owner can see it; a self-trigger and a false condition are only a firing
row; successful firings are visible through their commands' source.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, text

from tl_core.auth.projector import ACCOUNT_STREAM_TYPE
from tl_core.integration.automation import (
    ServerFields,
    plan_command,
    run_automation_command,
)
from tl_core.integration.contract import (
    RULE_BATCH_EVENTS,
    RULE_BINDINGS,
    RULE_MAX_CAUSATION_DEPTH,
    RULE_MAX_COMMANDS_PER_EVENT,
    RULE_MAX_RULES_PER_EVENT,
    AutomationAccess,
    CommandRunner,
    FiringOutcome,
    PlannedCommand,
    Problem,
    RuleMode,
    RuleStep,
)
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.rules.placeholders import substitute
from tl_core.integration.streams import (
    INTEGRATION_INTERNAL_EVENT_TYPES,
    RULE_BLOCKED,
    RULE_STREAM_TYPE,
)
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.services import proposals
from tl_core.services.commands import Command
from tl_core.services.errors import RetryableTransactionError, ServiceError
from tl_core.uow import UnitOfWork
from tl_core.webhooks.base import Clock, UowFactory, iso_z, utc_now
from tl_core.webhooks.dispatch import record_matches
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import OUTBOX_COLUMNS, OutboxRow, as_list, as_object, load_json

CURSOR_NAME = "rules"
#: ``rule:<key>@<version>/d<depth>``: what a rule stamps on the events of its commands.
SOURCE_RE = re.compile(r"rule:([a-z][a-z0-9_-]{0,62})@(\d{1,9})/d(\d{1,3})")
MAX_MESSAGE = 200


def rule_source(key: str, version: int, depth: int) -> str:
    """The ``source`` of the events a rule's commands make at ``depth``."""
    return f"rule:{key}@{version}/d{depth}"


def depth_of(source: str) -> tuple[str | None, int]:
    """``(rule key, depth)`` named by an event source; ``(None, 0)`` for any other source."""
    match = SOURCE_RE.fullmatch(source)
    if match is None:
        return None, 0
    return match.group(1), int(match.group(3))


#: How many causes back the chain of an event is followed (a rule hop is at most this deep).
MAX_CHAIN_WALK = 12
_CAUSE_SQL = text("SELECT source, causation_id FROM events WHERE event_id = :id")


def causal_chain(conn: Connection, row: OutboxRow) -> tuple[list[str], int]:
    """The rules on the causation chain of an event, and the deepest ``/d<n>`` found.

    The chain is ``row`` and its causes, followed through ``causation_id`` (a rule's command is
    caused by the event that matched; an action's events by the request; an accepted proposal by
    its creation). Every event whose source is ``rule:<key>@<version>/d<depth>`` adds its key.
    Depth is the larger of the number of rule hops and the largest ``d<depth>`` seen, so a loop that
    goes through an action or a proposal is cut as surely as one made of rules alone (FANOUT D7).
    The walk reads at most ``MAX_CHAIN_WALK`` events.
    """
    keys: list[str] = []
    deepest = 0
    own = conn.execute(_CAUSE_SQL, {"id": row.event_id}).first()
    source = row.source
    cause = None if own is None else own.causation_id
    for _ in range(MAX_CHAIN_WALK):
        key, depth = depth_of(source)
        if key is not None:
            keys.append(key)
            deepest = max(deepest, depth)
        if cause is None:
            break
        found = conn.execute(_CAUSE_SQL, {"id": cause}).first()
        if found is None:
            break
        source, cause = str(found.source), found.causation_id
    return keys, max(len(keys), deepest)


@dataclass(frozen=True)
class StoredRule:
    """A row of ``cur_rule`` as the worker needs it."""

    rule_id: str
    key: str
    title: str
    scope: str
    version: int
    when: WebhookFilter
    condition: str | None
    steps: tuple[RuleStep, ...]
    mode: RuleMode
    service_actor: str
    access: AutomationAccess
    enabled: bool
    enabled_from_seq: int
    integration_app: str | None

    @property
    def proposer(self) -> str:
        return self.service_actor


@dataclass
class FiringPlan:
    """What one rule would do for one event."""

    outcome: FiringOutcome
    depth: int
    commands: list[Command] = field(default_factory=list[Command])
    planned: list[PlannedCommand] = field(default_factory=list[PlannedCommand])
    problems: list[Problem] = field(default_factory=list[Problem])
    #: Whether the owner sees it as a ``Rule.Blocked`` event (a self-trigger and a false condition
    #: are only a firing row).
    announce: bool = False


@dataclass
class RuleStats:
    read: int = 0
    fired: int = 0
    proposed: int = 0
    blocked: int = 0
    killed: int = 0
    cursor: int = 0


_RULE_SQL = (
    "SELECT r.rule_id, r.key, r.title, r.scope, r.version, r.when_json, r.condition, r.then_json, "
    "r.mode, r.service_actor, r.access, r.enabled, r.enabled_from_seq, r.integration_app "
    "FROM cur_rule r WHERE r.enabled = :on "
    "AND (r.integration_app IS NULL OR r.integration_app IN "
    "(SELECT a.name FROM cur_integration_app a WHERE a.enabled = :on)) ORDER BY r.key"
)
_ONE_RULE_SQL = (
    "SELECT r.rule_id, r.key, r.title, r.scope, r.version, r.when_json, r.condition, r.then_json, "
    "r.mode, r.service_actor, r.access, r.enabled, r.enabled_from_seq, r.integration_app "
    "FROM cur_rule r WHERE r.rule_id = :id"
)
_LIVE_RULE_SQL = (
    "SELECT r.rule_id, r.key, r.title, r.scope, r.version, r.when_json, r.condition, r.then_json, "
    "r.mode, r.service_actor, r.access, r.enabled, r.enabled_from_seq, r.integration_app "
    "FROM cur_rule r WHERE r.rule_id = :id AND r.enabled = :on "
    "AND (r.integration_app IS NULL OR r.integration_app IN "
    "(SELECT a.name FROM cur_integration_app a WHERE a.enabled = :on))"
)
_FIRING_EXISTS = text("SELECT 1 FROM rule_firing WHERE rule_id = :rule_id AND event_id = :event_id")
_FIRING_INSERT = text(
    "INSERT INTO rule_firing (firing_id, rule_id, rule_version, event_id, seq, depth, outcome, "
    "command_count, fired_at) VALUES (:firing_id, :rule_id, :rule_version, :event_id, :seq, "
    ":depth, :outcome, :command_count, :fired_at) ON CONFLICT DO NOTHING"
)
_SUBJECT_SQL = text("SELECT key, title, type FROM cur_core_record WHERE id = :id")


def stored_rule(row: Any) -> StoredRule:
    """A ``StoredRule`` from a ``cur_rule`` mapping (a stored row is trusted: it was validated
    when it was written; a row that no longer parses raises and the worker stops on it)."""
    steps = tuple(RuleStep.model_validate(item) for item in as_list(load_json(row["then_json"])))
    return StoredRule(
        rule_id=row["rule_id"],
        key=row["key"],
        title=row["title"],
        scope=row["scope"],
        version=int(row["version"]),
        when=WebhookFilter.from_dict(as_object(load_json(row["when_json"]))),
        condition=row["condition"],
        steps=steps,
        mode=row["mode"],
        service_actor=row["service_actor"],
        access=row["access"],
        enabled=bool(row["enabled"]),
        enabled_from_seq=int(row["enabled_from_seq"]),
        integration_app=row["integration_app"],
    )


def load_rules(conn: Connection) -> list[StoredRule]:
    """The enabled rules whose app (when they have one) is enabled, in key order."""
    found = conn.execute(text(_RULE_SQL), {"on": True}).mappings()
    return [stored_rule(row) for row in found]


def load_live_rule(conn: Connection, rule_id: str) -> StoredRule | None:
    """The rule as it is **now**, or ``None`` when it is switched off or its app is.

    The worker loads its rules once per batch; a firing asks again inside its own unit of work, so
    switching a rule off (or revising it) takes effect at the next event, not at the next batch.
    """
    row = (
        conn.execute(
            text(_LIVE_RULE_SQL),
            {"on": True, "id": rule_id},
        )
        .mappings()
        .first()
    )
    return None if row is None else stored_rule(row)


def load_rule(conn: Connection, rule_id: str) -> StoredRule | None:
    """One rule by id, enabled or not."""
    row = conn.execute(text(_ONE_RULE_SQL), {"id": rule_id}).mappings().first()
    return None if row is None else stored_rule(row)


def read_outbox(conn: Connection, after: int, limit: int) -> list[OutboxRow]:
    """Outbox rows with ``seq > after``, oldest first."""
    sql = f"SELECT {OUTBOX_COLUMNS} FROM outbox_events WHERE seq > :after ORDER BY seq LIMIT :limit"
    found = conn.execute(text(sql), {"after": after, "limit": limit}).mappings()
    return [OutboxRow.from_mapping(row) for row in found]


def applies(rule: StoredRule, row: OutboxRow) -> bool:
    """The row-level part of *when*: scope, the moment the rule was switched on, the filter.

    The filter's ``record_selector`` and the rule's condition need the database and are judged by
    :func:`plan_firing`.
    """
    if row.stream_type == ACCOUNT_STREAM_TYPE or row.event_type in INTEGRATION_INTERNAL_EVENT_TYPES:
        return False  # account events and the layer's own bookkeeping are never offered to a rule
    if rule.scope != "company" and rule.scope != row.scope:
        return False
    if row.seq <= rule.enabled_from_seq:
        return False
    return rule.when.matches_row(row)


def bindings_of(conn: Connection, row: OutboxRow) -> dict[str, str]:
    """The values of ``RULE_BINDINGS`` for an event: the event and its subject record."""
    subject = conn.execute(_SUBJECT_SQL, {"id": row.subject_id}).first()
    values = {
        "event_id": row.event_id,
        "event_type": row.event_type,
        "event_actor": row.actor,
        "event_scope": row.scope,
        "subject_id": row.subject_id,
        "subject_key": (subject.key if subject is not None else row.subject_key) or "",
        "subject_title": (subject.title if subject is not None else "") or "",
        "subject_type": (subject.type if subject is not None else row.subject_type) or "",
    }
    assert set(values) == RULE_BINDINGS
    return values


def plan_firing(
    uow: UnitOfWork,
    runner: CommandRunner,
    rule: StoredRule,
    row: OutboxRow,
    *,
    commands_used: int = 0,
) -> FiringPlan | None:
    """What ``rule`` does for ``row``; ``None`` when the event does not match its *when*.

    Nothing is written. ``commands_used`` is what earlier rules already spent of the event's
    ``RULE_MAX_COMMANDS_PER_EVENT``.
    """
    if not applies(rule, row):
        return None
    selector = rule.when.record_selector
    if selector is not None and not record_matches(uow, row, selector):
        return None
    _, depth_in = causal_chain(uow.conn(), row)
    if depth_of(row.source)[0] == rule.key:
        return FiringPlan(
            "refused",
            depth_in,
            problems=[
                Problem(code="self_trigger", message="A rule does not fire on its own work.")
            ],
        )
    if depth_in >= RULE_MAX_CAUSATION_DEPTH:
        return FiringPlan(
            "depth_limit",
            depth_in,
            problems=[
                Problem(
                    code="depth_limit",
                    message=f"The causation depth limit of {RULE_MAX_CAUSATION_DEPTH} was reached.",
                )
            ],
            announce=True,
        )
    if rule.condition is not None and not record_matches(uow, row, rule.condition):
        return FiringPlan("skipped_condition", depth_in)
    if commands_used + len(rule.steps) > RULE_MAX_COMMANDS_PER_EVENT:
        return FiringPlan(
            "budget",
            depth_in,
            problems=[
                Problem(
                    code="budget",
                    message=f"At most {RULE_MAX_COMMANDS_PER_EVENT} commands per event.",
                )
            ],
            announce=True,
        )
    depth_out = depth_in + 1
    fields = ServerFields(
        actor=rule.service_actor,
        source=rule_source(rule.key, rule.version, depth_out) if rule.mode == "act" else "proposal",
        scope=row.scope,
        correlation_id=row.correlation_id,
        causation_id=row.event_id,
    )
    allowed = {step.command for step in rule.steps}
    bindings = bindings_of(uow.conn(), row)
    plan = FiringPlan("proposed" if rule.mode == "propose" else "fired", depth_in)
    for step in rule.steps:
        args, problem = substitute(step.args, bindings)
        if problem is not None:
            plan.planned.append(
                PlannedCommand(command_type=step.command, summary=step.command, problem=problem)
            )
            plan.problems.append(problem)
            continue
        built = plan_command(
            runner,
            step.command,
            args,
            fields,
            declared=rule.access,
            allowed=allowed,
            link_source="rule",
        )
        plan.planned.append(built.planned)
        if built.command is not None:
            plan.commands.append(built.command)
        elif built.planned.problem is not None:
            plan.problems.append(built.planned.problem)
    if plan.problems:
        plan.outcome = "refused"
        plan.commands = []
        plan.announce = True
    return plan


def _short(exc: Exception) -> Problem:
    """A fixed-shape problem for an error a command raised: a service error's own words, else
    only its type (anything else may hold a value or a path)."""
    if isinstance(exc, ServiceError):
        return Problem(code="command_refused", message=f"{type(exc).__name__}: {exc}"[:MAX_MESSAGE])
    if isinstance(exc, ValidationError):
        return Problem(code="invalid_command", message="A command of the rule is not valid.")
    if isinstance(exc, ConcurrencyError):
        return Problem(code="stale", message="The record changed under the rule.")
    return Problem(code="command_failed", message=f"A command failed ({type(exc).__name__}).")


class RulesWorker:
    """Follows the ledger and runs the rules. One instance per process; safe to run twice."""

    def __init__(
        self, open_uow: UowFactory, runner: CommandRunner, *, clock: Clock = utc_now
    ) -> None:
        self._open = open_uow
        self._runner = runner
        self._clock = clock

    # --- the loop ---------------------------------------------------------------------------

    def run_once(self, *, limit: int = RULE_BATCH_EVENTS) -> RuleStats:
        """Process up to ``limit`` events after the cursor and move the cursor past them."""
        with self._open() as uow:
            cursor = self._cursor(uow.conn())
            rows = read_outbox(uow.conn(), cursor, limit)
            rules = load_rules(uow.conn())
        stats = RuleStats(read=len(rows), cursor=cursor)
        for row in rows:
            self._event(row, rules, stats)
            stats.cursor = row.seq
        if stats.cursor != cursor:
            with self._open() as uow:
                self._set_cursor(uow.conn(), stats.cursor)
        return stats

    def run_until_idle(self, *, limit: int = RULE_BATCH_EVENTS) -> RuleStats:
        """Repeat :meth:`run_once` until a pass finds nothing."""
        total = RuleStats()
        while True:
            stats = self.run_once(limit=limit)
            total.read += stats.read
            total.fired += stats.fired
            total.proposed += stats.proposed
            total.blocked += stats.blocked
            total.killed += stats.killed
            total.cursor = max(total.cursor, stats.cursor)
            if stats.read == 0:
                return total

    # --- one event --------------------------------------------------------------------------

    def _event(self, row: OutboxRow, rules: Sequence[StoredRule], stats: RuleStats) -> None:
        used = 0
        matched = [rule for rule in rules if applies(rule, row)]
        for index, rule in enumerate(matched):
            if index >= RULE_MAX_RULES_PER_EVENT:
                self._record(
                    rule,
                    row,
                    "budget",
                    0,
                    0,
                    stats,
                    announce=True,
                    problems=[
                        Problem(
                            code="budget",
                            message=f"At most {RULE_MAX_RULES_PER_EVENT} rules per event.",
                        )
                    ],
                )
                continue
            used += self._fire(rule, row, used, stats)

    def _fire(self, rule: StoredRule, row: OutboxRow, used: int, stats: RuleStats) -> int:
        """One rule for one event in one unit of work; returns the commands it ran."""
        try:
            with self._open() as uow:
                if (
                    uow.conn()
                    .execute(_FIRING_EXISTS, {"rule_id": rule.rule_id, "event_id": row.event_id})
                    .first()
                ):
                    return 0
                live = load_live_rule(uow.conn(), rule.rule_id)
                if live is None:  # switched off since the batch was loaded: pass the event over
                    return 0
                rule = live
                if kill_switch_on(uow.conn()):
                    self._write_firing(uow, rule, row, "killed", 0, 0)
                    stats.killed += 1
                    return 0
                plan = plan_firing(uow, self._runner, rule, row, commands_used=used)
                if plan is None:
                    return 0
                if plan.outcome in ("fired", "proposed"):
                    self._execute(uow, rule, row, plan)
                    self._write_firing(uow, rule, row, plan.outcome, plan.depth, len(plan.commands))
                    if plan.outcome == "fired":
                        stats.fired += 1
                    else:
                        stats.proposed += 1
                    return len(plan.commands)
                self._write_firing(uow, rule, row, plan.outcome, plan.depth, 0)
                if plan.announce:
                    self._announce(uow, rule, row, plan.outcome, plan.depth, plan.problems)
                    stats.blocked += 1
                return 0
        except RetryableTransactionError:
            raise
        except Exception as exc:  # the commands are rolled back with the unit of work
            problem = _short(exc)
            _, depth_in = depth_of(row.source)
            self._record(
                rule, row, "refused", depth_in, 0, stats, announce=True, problems=[problem]
            )
            return 0

    def _execute(self, uow: UnitOfWork, rule: StoredRule, row: OutboxRow, plan: FiringPlan) -> None:
        if rule.mode == "act":
            for command in plan.commands:
                run_automation_command(
                    self._runner, uow, command, link_source="rule", declared=rule.access
                )
            return
        for command, planned in zip(plan.commands, plan.planned, strict=False):
            proposals.propose_for_rule(
                uow,
                proposer=rule.proposer,
                command=command,
                summary=f"{rule.title}: {planned.command_type}"[:300],
                trigger_event_id=row.event_id,
                correlation_id=row.correlation_id,
            )

    # --- records of what happened -----------------------------------------------------------

    def _record(
        self,
        rule: StoredRule,
        row: OutboxRow,
        outcome: FiringOutcome,
        depth: int,
        commands: int,
        stats: RuleStats,
        *,
        announce: bool,
        problems: list[Problem],
    ) -> None:
        """Write the firing row (and the ledger event) in a unit of work of its own.

        The rule's stream may move under an admin's edit; the write is tried three times.
        """
        for attempt in range(3):
            try:
                with self._open() as uow:
                    self._write_firing(uow, rule, row, outcome, depth, commands)
                    if announce:
                        self._announce(uow, rule, row, outcome, depth, problems)
                break
            except ConcurrencyError:
                if attempt == 2:
                    raise
        stats.blocked += 1

    def _write_firing(
        self,
        uow: UnitOfWork,
        rule: StoredRule,
        row: OutboxRow,
        outcome: FiringOutcome,
        depth: int,
        commands: int,
    ) -> None:
        uow.conn().execute(
            _FIRING_INSERT,
            {
                "firing_id": f"{rule.rule_id}:{rule.version}:{row.event_id}",
                "rule_id": rule.rule_id,
                "rule_version": rule.version,
                "event_id": row.event_id,
                "seq": row.seq,
                "depth": depth,
                "outcome": outcome,
                "command_count": commands,
                "fired_at": iso_z(self._clock()),
            },
        )

    def _announce(
        self,
        uow: UnitOfWork,
        rule: StoredRule,
        row: OutboxRow,
        outcome: FiringOutcome,
        depth: int,
        problems: Sequence[Problem],
    ) -> None:
        """``Rule.Blocked`` on the rule's stream, so its owner can see why it did not run."""
        version = (
            uow.conn()
            .execute(
                text("SELECT COALESCE(MAX(stream_version), 0) FROM events WHERE stream_id = :s"),
                {"s": rule.rule_id},
            )
            .scalar_one()
        )
        uow.append(
            stream_id=rule.rule_id,
            stream_type=RULE_STREAM_TYPE,
            scope=rule.scope,
            expected_version=int(version),
            events=[
                NewEvent(
                    event_type=RULE_BLOCKED,
                    payload={
                        "rule_id": rule.rule_id,
                        "rule_version": rule.version,
                        "trigger_event_id": row.event_id,
                        "trigger_seq": row.seq,
                        "depth": depth,
                        "outcome": outcome,
                        "problems": [p.model_dump() for p in problems],
                    },
                )
            ],
            actor=rule.service_actor,
            source=rule_source(rule.key, rule.version, depth),
            correlation_id=row.correlation_id,
            causation_id=row.event_id,
        )

    # --- cursor -----------------------------------------------------------------------------

    @staticmethod
    def _cursor(conn: Connection) -> int:
        row = conn.execute(
            text("SELECT last_seq FROM rule_cursor WHERE name = :n"), {"n": CURSOR_NAME}
        ).first()
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO rule_cursor (name, last_seq) VALUES (:n, 0) ON CONFLICT DO NOTHING"
                ),
                {"n": CURSOR_NAME},
            )
            return 0
        return int(row.last_seq)

    @staticmethod
    def _set_cursor(conn: Connection, seq: int) -> None:
        conn.execute(
            text("UPDATE rule_cursor SET last_seq = :seq WHERE name = :n AND last_seq < :seq"),
            {"seq": seq, "n": CURSOR_NAME},
        )


__all__ = [
    "CURSOR_NAME",
    "FiringPlan",
    "RuleStats",
    "RulesWorker",
    "StoredRule",
    "applies",
    "causal_chain",
    "depth_of",
    "load_live_rule",
    "load_rule",
    "load_rules",
    "plan_firing",
    "read_outbox",
    "rule_source",
]
