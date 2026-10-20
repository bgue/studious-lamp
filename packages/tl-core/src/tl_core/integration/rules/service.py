"""Authoring rules: create, revise, enable, disable (brief §18.8; FANOUT D7, D12).

All four are admin commands (the API table declares ``admin``; the handlers do not check roles).
A rule starts **disabled and in ``propose`` mode**; switching to ``act`` is a revision with a
reason. Every change is a new ``version`` that carries the whole rule, so the row is replaced by
what the event says. The rule's service actor is made here from its key (``svc:rule-<key>``): a
client cannot name another actor.

A stored rule must be one the worker can run: a filter that narrows (an empty ``when`` would match
every event), a condition that parses, steps of commands automation may run, and placeholders that
name a binding. What a step's arguments mean for a command is judged by the command's own model
when the rule runs, and by ``DryRunRule`` before then.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, ValidationError, field_validator
from sqlalchemy import text

from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    RULE_MAX_CONDITION_CHARS,
    SLUG_RE,
    AutomationAccess,
    Problem,
    Rule,
    RuleMode,
)
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.rules.placeholders import check_template
from tl_core.integration.streams import (
    RULE_CREATED,
    RULE_DISABLED,
    RULE_ENABLED,
    RULE_REVISED,
    RULE_STREAM_TYPE,
)
from tl_core.ledger import NewEvent
from tl_core.query.api import QuerySyntaxError, parse
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import as_list, as_object, load_json

#: What a revision may change. The key, the scope and the service actor are the rule's identity.
REVISABLE = frozenset(
    {"title", "when", "condition", "then", "mode", "access", "owner", "integration_app"}
)
_MAX_REASON = 1_000


def _check_reason(value: str | None) -> str | None:
    if value is not None and (not value.strip() or len(value) > _MAX_REASON):
        raise ValueError(f"reason must be 1 to {_MAX_REASON} characters")
    return value


class CreateRule(Command):
    """A new rule. It starts disabled and in ``propose`` mode."""

    key: str
    title: str = Field(min_length=1, max_length=200)
    when: dict[str, Any]
    condition: str | None = Field(default=None, max_length=RULE_MAX_CONDITION_CHARS)
    then: list[dict[str, Any]]
    access: AutomationAccess = "user"
    owner: str | None = None  # defaults to the actor
    integration_app: str | None = None


class ReviseRule(Command):
    """A new version of a rule. ``reason`` says why; ``expected_version`` is the ledger stream
    version the caller read (None: whatever it is now)."""

    rule_id: str
    changes: dict[str, Any]
    reason: str
    expected_version: int | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _check_reason(value) or ""


class EnableRule(Command):
    rule_id: str
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _check_reason(value)


class DisableRule(EnableRule): ...


def rule_problems(rule: Rule) -> list[Problem]:
    """Why ``rule`` cannot be stored (empty means it can)."""
    problems: list[Problem] = []
    if SLUG_RE.fullmatch(rule.key) is None:
        problems.append(Problem(code="bad_key", message="A key is a slug: a-z, 0-9, - and _."))
    try:
        parsed = WebhookFilter.from_dict(rule.when)
    except ValueError as exc:
        problems.append(Problem(code="bad_when", message=f"when: {exc}"[:200]))
    else:
        if not parsed.to_dict():
            problems.append(
                Problem(
                    code="when_too_wide",
                    message="when must narrow: an empty filter is every event.",
                )
            )
    if rule.condition is not None:
        try:
            parse(rule.condition)
        except QuerySyntaxError as exc:
            problems.append(Problem(code="bad_condition", message=f"condition: {exc}"[:200]))
    for number, step in enumerate(rule.then, start=1):
        for problem in check_template(step.args):
            problems.append(
                Problem(code=problem.code, message=f"step {number}: {problem.message}"[:200])
            )
    return problems


def _require_valid(rule: Rule) -> None:
    problems = rule_problems(rule)
    if problems:
        raise InvalidIntegrationError("; ".join(p.message for p in problems)[:500])


def _row(uow: UnitOfWork, rule_id: str, scope: str) -> Any:
    row = (
        uow.conn()
        .execute(text("SELECT * FROM cur_rule WHERE rule_id = :i"), {"i": rule_id})
        .mappings()
        .first()
    )
    if row is None or row["scope"] != scope:
        raise IntegrationNotFoundError(f"no rule {rule_id} in {scope}")
    return row


def _app_must_exist(uow: UnitOfWork, app: str | None) -> None:
    if app is None:
        return
    found = (
        uow.conn()
        .execute(text("SELECT 1 FROM cur_integration_app WHERE name = :n"), {"n": app})
        .first()
    )
    if found is None:
        raise InvalidIntegrationError(f"no integration app named {app}")


def rule_of_row(row: Any) -> Rule:
    """The contract model of a stored row."""
    return Rule.model_validate(
        {
            "key": row["key"],
            "title": row["title"],
            "scope": row["scope"],
            "version": int(row["version"]),
            "when": as_object(load_json(row["when_json"])),
            "condition": row["condition"],
            "then": as_list(load_json(row["then_json"])),
            "mode": row["mode"],
            "service_actor": row["service_actor"],
            "access": row["access"],
            "owner": row["owner"],
            "enabled": bool(row["enabled"]),
        }
    )


def handle_create_rule(uow: UnitOfWork, cmd: CreateRule) -> CommandResult:
    try:
        rule = Rule.model_validate(
            {
                "key": cmd.key,
                "title": cmd.title,
                "scope": cmd.scope,
                "when": cmd.when,
                "condition": cmd.condition,
                "then": cmd.then,
                "mode": "propose",
                "service_actor": f"svc:rule-{cmd.key}",
                "access": cmd.access,
                "owner": cmd.owner or cmd.actor,
                "enabled": False,
            }
        )
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _require_valid(rule)
    _app_must_exist(uow, cmd.integration_app)
    taken = (
        uow.conn().execute(text("SELECT 1 FROM cur_rule WHERE key = :k"), {"k": rule.key}).first()
    )
    if taken is not None:
        raise DuplicateIntegrationError(f"a rule with the key {rule.key} exists")
    rule_id = new_ulid()
    payload = {
        "rule_id": rule_id,
        **rule.model_dump(mode="json", exclude={"scope"}),
        "integration_app": cmd.integration_app,
    }
    result = uow.append(
        stream_id=rule_id,
        stream_type=RULE_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=0,
        events=[NewEvent(event_type=RULE_CREATED, payload=payload)],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=rule_id, key=rule.key, version=result.new_version, events=result.events
    )


def handle_revise_rule(uow: UnitOfWork, cmd: ReviseRule) -> CommandResult:
    row = _row(uow, cmd.rule_id, cmd.scope)
    unknown = sorted(set(cmd.changes) - REVISABLE)
    if unknown:
        raise InvalidIntegrationError(f"a rule's {', '.join(unknown)} cannot be changed")
    if not cmd.changes:
        raise InvalidIntegrationError("nothing to change")
    current = rule_of_row(row).model_dump(mode="json")
    merged = {**current, **{k: v for k, v in cmd.changes.items() if k != "integration_app"}}
    merged["version"] = int(row["version"]) + 1
    try:
        rule = Rule.model_validate(merged)
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _require_valid(rule)
    app = cmd.changes.get("integration_app", row["integration_app"])
    _app_must_exist(uow, app)
    if rule.model_dump(mode="json") == {**current, "version": rule.version}:
        raise InvalidIntegrationError("nothing changes")
    expected = (
        cmd.expected_version if cmd.expected_version is not None else int(row["stream_version"])
    )
    result = uow.append(
        stream_id=cmd.rule_id,
        stream_type=RULE_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[
            NewEvent(
                event_type=RULE_REVISED,
                payload={
                    "rule_id": cmd.rule_id,
                    "version": rule.version,
                    "rule": {
                        **rule.model_dump(mode="json", exclude={"scope"}),
                        "integration_app": app,
                    },
                    "reason": cmd.reason.strip(),
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.rule_id, key=rule.key, version=result.new_version, events=result.events
    )


def _switch(uow: UnitOfWork, cmd: EnableRule, *, on: bool) -> CommandResult:
    row = _row(uow, cmd.rule_id, cmd.scope)
    if bool(row["enabled"]) is on:
        raise IntegrationStateError(f"rule {row['key']} is already {'on' if on else 'off'}")
    if on:
        _require_valid(rule_of_row(row))  # a rule stored before a stricter check does not start
    result = uow.append(
        stream_id=cmd.rule_id,
        stream_type=RULE_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=int(row["stream_version"]),
        events=[
            NewEvent(
                event_type=RULE_ENABLED if on else RULE_DISABLED,
                payload={"rule_id": cmd.rule_id, "reason": cmd.reason},
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.rule_id, key=row["key"], version=result.new_version, events=result.events
    )


def handle_enable_rule(uow: UnitOfWork, cmd: EnableRule) -> CommandResult:
    return _switch(uow, cmd, on=True)


def handle_disable_rule(uow: UnitOfWork, cmd: DisableRule) -> CommandResult:
    return _switch(uow, cmd, on=False)


__all__ = [
    "REVISABLE",
    "CreateRule",
    "DisableRule",
    "EnableRule",
    "ReviseRule",
    "RuleMode",
    "handle_create_rule",
    "handle_disable_rule",
    "handle_enable_rule",
    "handle_revise_rule",
    "rule_of_row",
    "rule_problems",
]
