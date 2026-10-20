"""The actions registry: define, revise, retire, rotate a secret, invoke (brief §18.7; FANOUT D8).

**Definitions** are admin commands. A definition names an executor of Phase 1 (``job`` or
``webhook``); a definition naming another is refused (``executor_unavailable``). A ``job`` names an
installed job (found by entry point, never user code). A ``webhook`` gets its signing secret from
the server: the text is returned once with the result and kept only in ``int_secret``; a
``secret_id`` supplied by the client is refused. The URL is checked by the egress policy now and
again at every attempt.

**Invoking** (``InvokeAction``) checks, in this order: the action exists, is not retired, and its
app is on; the caller holds the definition's ``access`` (``holds``, a Python argument from the
client layer, never a request field); the action applies to every target (scope, record type glob,
condition) and the parameters fit the definition; then either the invocation is requested
(``Action.Requested`` on a new ``core.ActionInvocation`` stream, plus a job of kind ``action``) or,
when the definition ``requires_approval``, a proposal is recorded that **another person** with that
access accepts; accepting runs this same handler with the approval.

The execution is the job kind in ``actions/jobs.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import Field, ValidationError
from sqlalchemy import text

from tl_core import confidentiality
from tl_core.changefeed.filters import glob_match
from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    ACTION_MAX_ATTEMPTS,
    ACTION_MAX_PARAMETERS_BYTES,
    ACTION_MAX_TARGETS,
    PHASE1_EXECUTORS,
    SLUG_RE,
    ActionDefinition,
    ActionParameter,
    InvokeAction,
    JobExecutorConfig,
    Problem,
    RecordRef,
    WebhookExecutorConfig,
)
from tl_core.integration.errors import (
    ActionAccessError,
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.executors.job import has_job
from tl_core.integration.killswitch import kill_switch_on
from tl_core.integration.secrets import IssuedSecret, issue_secret, rotate_secret
from tl_core.integration.streams import (
    ACTION_DEFINED,
    ACTION_DEFINITION_STREAM_TYPE,
    ACTION_INVOCATION_STREAM_TYPE,
    ACTION_REQUESTED,
    ACTION_RETIRED,
    ACTION_REVISED,
    ACTION_SECRET_ROTATED,
)
from tl_core.jobs.queue import JobQueue
from tl_core.ledger import Event, NewEvent
from tl_core.query.api import QuerySpec, QuerySyntaxError, count_query, parse
from tl_core.query.ast import And, Compare
from tl_core.services import proposals
from tl_core.services.commands import Command, CommandResult
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow
from tl_core.webhooks.egress import (
    SETTING_ALLOWLIST,
    EgressDenied,
    EgressPolicy,
    ResolutionFailed,
)
from tl_core.webhooks.rows import as_list, as_object, load_json
from tl_core.webhooks.subscriptions import validate_target_url

Holds = Callable[[str], bool]
JOB_KIND = "action"
#: What a revision may change. The name, the scope, the executor kind and the secret are the
#: definition's identity.
REVISABLE = frozenset(
    {
        "label",
        "description",
        "applies_to",
        "parameters",
        "executor_config",
        "side_effect_class",
        "requires_approval",
        "access",
        "result_handling",
        "owner",
        "enabled",
        "integration_app",
    }
)
_MAX_REASON = 1_000


class DefineAction(Command):
    """A new action. ``executor_config`` has no ``secret_id``: the server makes the secret."""

    name: str
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    applies_to: dict[str, Any] = Field(default_factory=dict[str, Any])
    parameters: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    executor: str
    executor_config: dict[str, Any]
    side_effect_class: str
    requires_approval: bool = False
    access: str = "user"
    result_handling: list[str] = Field(default_factory=lambda: ["store"])
    owner: str | None = None
    integration_app: str | None = None


class ReviseAction(Command):
    definition_id: str
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=_MAX_REASON)
    expected_version: int | None = None


class RetireAction(Command):
    definition_id: str
    reason: str = Field(min_length=1, max_length=_MAX_REASON)


class RotateActionSecret(Command):
    definition_id: str
    overlap_hours: float = 24.0


@dataclass
class ActionDefined:
    """The result of defining an action or rotating its secret. ``secret`` is shown once."""

    definition_id: str
    secret_id: str | None
    version: int
    events: list[Event] = field(default_factory=list[Event])
    secret: IssuedSecret | None = field(default=None, repr=False)


# --- reading ----------------------------------------------------------------------------------

_DEFINITION_SQL = text(
    "SELECT d.* FROM cur_action_definition d WHERE d.name = :name AND (d.integration_app IS NULL "
    "OR d.integration_app IN (SELECT a.name FROM cur_integration_app a WHERE a.enabled = :on))"
)


def definition_row(conn: Any, name: str) -> dict[str, Any] | None:
    found = conn.execute(_DEFINITION_SQL, {"name": name, "on": True}).mappings().first()
    return None if found is None else dict(found)


def definition_of_row(row: dict[str, Any]) -> ActionDefinition:
    """The contract model of a stored row."""
    return ActionDefinition.model_validate(
        {
            "name": row["name"],
            "label": row["label"],
            "description": row["description"] or "",
            "scope": row["scope"],
            "version": int(row["version"]),
            "applies_to": as_object(load_json(row["applies_to_json"])),
            "parameters": as_list(load_json(row["parameters_json"])),
            "executor": row["executor"],
            "executor_config": as_object(load_json(row["executor_config_json"])),
            "side_effect_class": row["side_effect_class"],
            "requires_approval": bool(row["requires_approval"]),
            "access": row["access"],
            "result_handling": as_list(load_json(row["result_handling_json"])),
            "owner": row["owner"],
            "enabled": bool(row["enabled"]),
        }
    )


def _load(uow: UnitOfWork, definition_id: str, scope: str) -> dict[str, Any]:
    found = (
        uow.conn()
        .execute(
            text("SELECT * FROM cur_action_definition WHERE definition_id = :i"),
            {"i": definition_id},
        )
        .mappings()
        .first()
    )
    if found is None or found["scope"] != scope:
        raise IntegrationNotFoundError(f"no action {definition_id} in {scope}")
    return dict(found)


# --- definitions -------------------------------------------------------------------------------


def default_policy(uow: UnitOfWork) -> EgressPolicy:
    """The egress policy of the ``webhooks.egress.allowlist`` setting, with the system resolver."""
    return EgressPolicy.from_settings({SETTING_ALLOWLIST: value_of(uow.conn(), SETTING_ALLOWLIST)})


def definition_problems(definition: ActionDefinition, policy: EgressPolicy | None) -> list[Problem]:
    """Why ``definition`` cannot be stored (empty means it can). Needs no database."""
    problems: list[Problem] = []
    if SLUG_RE.fullmatch(definition.name) is None:
        problems.append(Problem(code="bad_name", message="A name is a slug: a-z, 0-9, - and _."))
    if definition.executor not in PHASE1_EXECUTORS:
        problems.append(
            Problem(
                code="executor_unavailable",
                message=f"The {definition.executor} executor is not built in this phase.",
            )
        )
    seen: set[str] = set()
    for parameter in definition.parameters:
        if parameter.name in seen:
            problems.append(Problem(code="duplicate_parameter", message=f"{parameter.name} twice."))
        seen.add(parameter.name)
    condition = definition.applies_to.condition
    if condition is not None:
        try:
            parse(condition)
        except QuerySyntaxError as exc:
            problems.append(Problem(code="bad_condition", message=f"applies_to: {exc}"[:200]))
    config = definition.executor_config
    if isinstance(config, JobExecutorConfig):
        if not has_job(config.job):
            problems.append(
                Problem(code="unknown_job", message=f"No job is installed as {config.job}.")
            )
    else:
        problems.extend(_url_problems(config, policy))
    return problems


def _url_problems(config: WebhookExecutorConfig, policy: EgressPolicy | None) -> list[Problem]:
    try:
        validate_target_url(config.url)
    except Exception:
        return [
            Problem(
                code="bad_url", message="The URL must be http(s) with a host and no credentials."
            )
        ]
    if policy is None:
        return []
    try:
        policy.check(config.url)
    except EgressDenied:
        return [Problem(code="egress_denied", message="The receiver's address is not allowed.")]
    except ResolutionFailed:
        return []  # the name may not exist yet; every attempt checks again
    return []


def _raise(problems: list[Problem]) -> None:
    if problems:
        raise InvalidIntegrationError("; ".join(p.message for p in problems)[:500])


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


def define_action(
    uow: UnitOfWork,
    cmd: DefineAction,
    *,
    policy: EgressPolicy | None = None,
    now: datetime | None = None,
) -> ActionDefined:
    """Store a new action; a webhook action gets its first secret (returned once)."""
    if "secret_id" in cmd.executor_config:
        raise InvalidIntegrationError("the server makes the secret; secret_id may not be supplied")
    try:
        definition = ActionDefinition.model_validate(
            {
                "name": cmd.name,
                "label": cmd.label,
                "description": cmd.description,
                "scope": cmd.scope,
                "applies_to": cmd.applies_to,
                "parameters": cmd.parameters,
                "executor": cmd.executor,
                "executor_config": {"kind": cmd.executor, **cmd.executor_config},
                "side_effect_class": cmd.side_effect_class,
                "requires_approval": cmd.requires_approval,
                "access": cmd.access,
                "result_handling": cmd.result_handling,
                "owner": cmd.owner or cmd.actor,
                "enabled": True,
            }
        )
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _raise(definition_problems(definition, policy if policy is not None else default_policy(uow)))
    _app_must_exist(uow, cmd.integration_app)
    taken = (
        uow.conn()
        .execute(
            text("SELECT 1 FROM cur_action_definition WHERE name = :n"), {"n": definition.name}
        )
        .first()
    )
    if taken is not None:
        raise DuplicateIntegrationError(f"an action named {definition.name} exists")
    definition_id = new_ulid()
    when = now or utcnow()
    issued: IssuedSecret | None = None
    payload = definition.model_dump(mode="json", exclude={"scope"})
    if isinstance(definition.executor_config, WebhookExecutorConfig):
        issued = issue_secret(uow.conn(), "action", definition_id, now=when)
        payload["executor_config"]["secret_id"] = issued.secret_id
    result = uow.append(
        stream_id=definition_id,
        stream_type=ACTION_DEFINITION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=ACTION_DEFINED,
                payload={
                    "definition_id": definition_id,
                    **payload,
                    "integration_app": cmd.integration_app,
                    "secret_id": None if issued is None else issued.secret_id,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return ActionDefined(
        definition_id=definition_id,
        secret_id=None if issued is None else issued.secret_id,
        version=result.new_version,
        events=result.events,
        secret=issued,
    )


def handle_revise_action(
    uow: UnitOfWork, cmd: ReviseAction, *, policy: EgressPolicy | None = None
) -> CommandResult:
    row = _load(uow, cmd.definition_id, cmd.scope)
    if bool(row["retired"]):
        raise IntegrationStateError(f"action {row['name']} is retired")
    unknown = sorted(set(cmd.changes) - REVISABLE)
    if unknown:
        raise InvalidIntegrationError(f"an action's {', '.join(unknown)} cannot be changed")
    if not cmd.changes:
        raise InvalidIntegrationError("nothing to change")
    current = definition_of_row(row).model_dump(mode="json")
    merged = {k: v for k, v in current.items()}
    for name, value in cmd.changes.items():
        if name == "integration_app":
            continue
        if name == "executor_config":
            config = dict(as_object(value))
            if "secret_id" in config:
                raise InvalidIntegrationError(
                    "the server makes the secret; secret_id may not be changed"
                )
            value = {"kind": current["executor"], **config}
            if current["executor"] == "webhook":
                value["secret_id"] = as_object(current["executor_config"]).get("secret_id")
        merged[name] = value
    merged["version"] = int(row["version"]) + 1
    try:
        definition = ActionDefinition.model_validate(merged)
    except ValidationError as exc:
        raise InvalidIntegrationError(first_error(exc)) from exc
    _raise(definition_problems(definition, policy if policy is not None else default_policy(uow)))
    app = cmd.changes.get("integration_app", row["integration_app"])
    _app_must_exist(uow, app)
    expected = (
        cmd.expected_version if cmd.expected_version is not None else int(row["stream_version"])
    )
    result = uow.append(
        stream_id=cmd.definition_id,
        stream_type=ACTION_DEFINITION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=expected,
        events=[
            NewEvent(
                event_type=ACTION_REVISED,
                payload={
                    "definition_id": cmd.definition_id,
                    "version": definition.version,
                    "definition": {
                        **definition.model_dump(mode="json", exclude={"scope"}),
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
        stream_id=cmd.definition_id,
        key=definition.name,
        version=result.new_version,
        events=result.events,
    )


def handle_retire_action(uow: UnitOfWork, cmd: RetireAction) -> CommandResult:
    row = _load(uow, cmd.definition_id, cmd.scope)
    if bool(row["retired"]):
        raise IntegrationStateError(f"action {row['name']} is already retired")
    result = uow.append(
        stream_id=cmd.definition_id,
        stream_type=ACTION_DEFINITION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=int(row["stream_version"]),
        events=[
            NewEvent(
                event_type=ACTION_RETIRED,
                payload={"definition_id": cmd.definition_id, "reason": cmd.reason.strip()},
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.definition_id,
        key=row["name"],
        version=result.new_version,
        events=result.events,
    )


def rotate_action_secret(
    uow: UnitOfWork, cmd: RotateActionSecret, *, now: datetime | None = None
) -> ActionDefined:
    """Issue a new signing secret (shown once); the previous one signs for the overlap."""
    row = _load(uow, cmd.definition_id, cmd.scope)
    if row["executor"] != "webhook" or row["secret_id"] is None:
        raise IntegrationStateError(f"action {row['name']} has no signing secret")
    rotation = rotate_secret(
        uow.conn(),
        "action",
        cmd.definition_id,
        now=now or utcnow(),
        overlap_hours=cmd.overlap_hours,
    )
    result = uow.append(
        stream_id=cmd.definition_id,
        stream_type=ACTION_DEFINITION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=int(row["stream_version"]),
        events=[
            NewEvent(
                event_type=ACTION_SECRET_ROTATED,
                payload={
                    "definition_id": cmd.definition_id,
                    "secret_id": rotation.issued.secret_id,
                    "previous_secret_id": rotation.previous_secret_id,
                    "previous_expires_at": rotation.previous_expires_at,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return ActionDefined(
        definition_id=cmd.definition_id,
        secret_id=rotation.issued.secret_id,
        version=result.new_version,
        events=result.events,
        secret=rotation.issued,
    )


# --- invoking ----------------------------------------------------------------------------------


def parameter_problems(parameters: list[ActionParameter], values: dict[str, Any]) -> list[Problem]:
    """Why ``values`` do not fit the definition's parameters (empty means they do)."""
    problems: list[Problem] = []
    declared = {p.name: p for p in parameters}
    try:
        size = len(json.dumps(values, sort_keys=True, separators=(",", ":")).encode())
    except (TypeError, ValueError, OverflowError, RecursionError):
        return [Problem(code="bad_parameters", message="The parameters must be JSON.")]
    if size > ACTION_MAX_PARAMETERS_BYTES:
        return [Problem(code="parameters_too_large", message="The parameters are too large.")]
    for name in sorted(set(values) - set(declared)):
        problems.append(Problem(code="unknown_parameter", message=f"No parameter {name[:40]}."))
    for name, parameter in declared.items():
        if name not in values or values[name] is None:
            if parameter.required:
                problems.append(Problem(code="missing_parameter", message=f"{name} is required."))
            continue
        problem = _kind_problem(parameter, values[name])
        if problem is not None:
            problems.append(Problem(code="bad_parameter", message=f"{name}: {problem}"))
    return problems


def _kind_problem(parameter: ActionParameter, value: Any) -> str | None:
    kind = parameter.kind
    if kind in ("string", "date", "record_ref"):
        if not isinstance(value, str):
            return "must be text"
        if parameter.max_length is not None and len(value) > parameter.max_length:
            return f"at most {parameter.max_length} characters"
        if kind == "date":
            try:
                datetime.fromisoformat(value)
            except ValueError:
                return "must be a date (YYYY-MM-DD)"
    elif kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return "must be a whole number"
    elif kind == "decimal":
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return "must be a number"
        try:
            Decimal(str(value))
        except InvalidOperation:
            return "must be a number"
    elif kind == "bool" and not isinstance(value, bool):
        return "must be true or false"
    if parameter.choices is not None and (
        not isinstance(value, str) or value not in parameter.choices
    ):
        return "must be one of the choices"
    return None


_RECORD_SQL = text(
    "SELECT id, key, type, scope, version, voided FROM cur_core_record WHERE id = :id"
)


def resolve_targets(
    uow: UnitOfWork, definition: ActionDefinition, targets: list[str], scope: str
) -> list[RecordRef]:
    """The targets as references, each checked against ``applies_to``. Raises
    ``InvalidIntegrationError`` for the first that does not fit; an unknown record or one of
    another scope is not found (one answer, so ids cannot be probed)."""
    if len(targets) > ACTION_MAX_TARGETS or len(set(targets)) != len(targets):
        raise InvalidIntegrationError(f"1 to {ACTION_MAX_TARGETS} different targets")
    refs: list[RecordRef] = []
    condition = (
        None if definition.applies_to.condition is None else parse(definition.applies_to.condition)
    )
    for record_id in targets:
        row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
        if (
            row is None
            or row.scope != scope
            or bool(row.voided)
            or confidentiality.is_hidden(uow.conn(), record_id)  # as absent as a missing record
        ):
            raise IntegrationNotFoundError("a target is not a record of this scope")
        if not any(glob_match(pattern, row.type) for pattern in definition.applies_to.record_types):
            raise InvalidIntegrationError(f"{definition.name} does not apply to {row.type} records")
        if condition is not None:
            where = And((Compare("id", "=", record_id), condition))
            spec = QuerySpec(scope=scope, where=where, limit=None)
            if count_query(uow, spec) == 0:
                raise InvalidIntegrationError(
                    f"{definition.name} does not apply to {row.key or record_id} now"
                )
        refs.append(
            RecordRef(id=row.id, key=row.key, record_type=row.type, version=int(row.version))
        )
    return refs


def handle_invoke_action(
    uow: UnitOfWork,
    cmd: InvokeAction,
    *,
    holds: Holds | None = None,
    proposal_id: str | None = None,
    invoked_by: str | None = None,
) -> CommandResult:
    """Request an action. ``holds`` says what access the person has (None: only ``user``).

    ``proposal_id`` and ``invoked_by`` are set only when an accepted proposal re-runs this handler:
    the approval is then given and the request is the original requester's.
    """
    if kill_switch_on(uow.conn()):  # nothing new is requested while the integrations are stopped
        raise IntegrationStateError("integrations are stopped (the kill switch is on)")
    row = definition_row(uow.conn(), cmd.action)
    if row is None or bool(row["retired"]) or not bool(row["enabled"]):
        raise IntegrationNotFoundError(f"no action named {cmd.action}")
    if row["scope"] != "company" and row["scope"] != cmd.scope:
        raise IntegrationNotFoundError(f"no action named {cmd.action}")
    definition = definition_of_row(row)
    level = definition.access
    allowed = level == "user" or (holds is not None and holds(level))
    if not allowed:
        raise ActionAccessError(f"{cmd.action} needs the {level} role")
    _raise(parameter_problems(definition.parameters, cmd.parameters))
    refs = resolve_targets(uow, definition, list(cmd.targets), cmd.scope)
    requester = invoked_by or cmd.actor
    if definition.requires_approval and proposal_id is None:
        view = proposals.propose_action(
            uow,
            proposer=requester,
            command=cmd,
            summary=f"{definition.label}: {len(refs)} record(s)"[:300],
        )
        return CommandResult(stream_id=view.proposal_id, key=None, version=1, events=[])
    invocation_id = new_ulid()
    result = uow.append(
        stream_id=invocation_id,
        stream_type=ACTION_INVOCATION_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type=ACTION_REQUESTED,
                payload={
                    "invocation_id": invocation_id,
                    "action": definition.name,
                    "action_version": definition.version,
                    "definition_id": row["definition_id"],
                    "targets": [ref.model_dump(mode="json") for ref in refs],
                    "parameters": cmd.parameters,
                    "invoked_by": requester,
                    "proposal_id": proposal_id,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    JobQueue().enqueue(
        uow.conn(),
        job_id=invocation_id,
        kind=JOB_KIND,
        scope=cmd.scope,
        now=utcnow(),
        max_attempts=ACTION_MAX_ATTEMPTS,
    )
    return CommandResult(
        stream_id=invocation_id, key=None, version=result.new_version, events=result.events
    )


__all__ = [
    "JOB_KIND",
    "REVISABLE",
    "ActionDefined",
    "DefineAction",
    "RetireAction",
    "ReviseAction",
    "RotateActionSecret",
    "default_policy",
    "define_action",
    "definition_of_row",
    "definition_problems",
    "definition_row",
    "handle_invoke_action",
    "handle_retire_action",
    "handle_revise_action",
    "parameter_problems",
    "resolve_targets",
    "rotate_action_secret",
]
