"""Integration-layer contracts for P1-I7 (brief §18.5, §18.7-§18.9, §19.2; ADR-0008 decision 8).

Frozen for the increment: change only by orchestrator decision (``docs/tickets/P1-I7/FANOUT.md``).

Four engines share these shapes:

* **Actions** (§18.7): an :class:`ActionDefinition` names an operation; :class:`InvokeAction`
  asks for it; an :class:`ActionExecutor` (Phase 1: ``job`` and ``webhook``) performs it and
  returns an :class:`ActionOutcome`.
* **Rules** (§18.8): a :class:`Rule` is *when* (a ``SubscriptionFilter``) -> *if* (a
  query-language condition on the subject record) -> *then* (:class:`RuleStep` commands), acted or
  proposed under a declared service actor, bounded per event and by causation depth.
* **Inbound endpoints** (§18.5): an :class:`InboundEndpoint` verifies a signed POST and maps the
  payload with a :class:`MappingRuntime` to :class:`MappedCommand` items, which only name commands
  in the endpoint's allow-list.
* **Enrichment** (§18.9): an :class:`Enricher` plugin proposes values in its own namespaced pset
  (the ``enrich.<enricher>`` layer) and proposed links; the service wraps them as
  :class:`EnrichmentValue` with provenance and an acceptance state. ADR-0008 decision 8: the
  first enricher is deterministic (no model, no spend).

Shared by both workstreams: :data:`Access`, :class:`CommandRunner`, :class:`PlannedCommand`,
:class:`Problem`, :class:`RecordRef`, :class:`InvokeAction`, the reserved identifier prefixes.
WS-B (threads) imports this module and nothing else of WS-A.

The LinkML classes that make these records storable are written in WS-A ticket T01 in
``schema/core/integration.yaml`` (records) and ``schema/core/integration_ops.yaml`` (operational
tables) with **the same slot names** as the models here; T01 adds a test that compares them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

# --------------------------------------------------------------------------------------------
# Access (ADR-0011, ADR-0013) and service actors (FANOUT D3)
# --------------------------------------------------------------------------------------------

#: Who may run a command: any signed-in person, an admin or a document controller, an admin.
Access = Literal["user", "controller", "admin"]
ACCESS_RANK: dict[str, int] = {"user": 0, "controller": 1, "admin": 2}
#: What a service actor (rule, inbound endpoint, enricher) may be declared to hold. Automation never
#: runs an ``admin`` command in Phase 1 (FANOUT D3).
AutomationAccess = Literal["user", "controller"]

#: ``svc:<kind>-<slug>``. Service actors are actor strings, not accounts (ADR-0009): the engine that
#: runs them checks the declared access against the access of each command it would run.
SERVICE_ACTOR_RE = re.compile(r"svc:(?:rule|inbound|enricher|action)-[a-z0-9][a-z0-9_.-]{0,80}")

#: A name a person types for an action, rule, endpoint, app or enricher.
SLUG_RE = re.compile(r"[a-z][a-z0-9_-]{0,62}")


def access_covers(held: str, needed: str | None) -> bool:
    """Whether ``held`` access is at least ``needed``. ``None`` (nothing declared) never is."""
    if needed is None or held not in ACCESS_RANK or needed not in ACCESS_RANK:
        return False
    return ACCESS_RANK[held] >= ACCESS_RANK[needed]


# --------------------------------------------------------------------------------------------
# Reserved identifiers (FANOUT D2): only the server sets these. WS-A wires them into
# ``tl_core.services.reserved`` and the link and pset services before WS-B merges.
# --------------------------------------------------------------------------------------------

#: Event sources the server sets for automation; a client command that carries one is refused.
RESERVED_SOURCE_PREFIXES = ("inbound:", "rule:", "enricher:", "action:", "thread:")
#: Correlation and causation ids the server sets for automation.
RESERVED_CORRELATION_PREFIXES = ("inbound:", "rule:", "action:", "dispatch:")
#: Link sources only a server path may claim. ``rule``, ``enricher``, ``import`` and ``mapping`` are
#: already reserved (ADR-0010 second addendum); ``thread_dispatch`` joins them.
RESERVED_LINK_SOURCES = ("rule", "enricher", "import", "mapping", "thread_dispatch")
#: The pset layer only the enrichment service writes: ``psets.enrich.<enricher>.<property>``.
#: Phase 0 already reserves it (``tl_core.services.psets.READ_ONLY_ROOTS``, layer ``enrichment`` in
#: ``tl_core.projection.pset.classify``); FANOUT D6.
ENRICHMENT_PSET_PREFIX = "enrich."
#: An enricher's name is one path segment of that layer.
ENRICHER_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,62}")
#: Command fields the server sets on everything automation runs. A mapping or a rule step that
#: names one is refused, never ignored.
SERVER_SET_FIELDS = frozenset(
    {"actor", "source", "scope", "correlation_id", "causation_id", "idempotency_key", "by_module"}
)

#: The commands automation (rule steps, inbound mappings) may produce in Phase 1. An endpoint's or a
#: rule's own list must be a subset. Nothing else, whatever access a service actor is declared to
#: hold. ``CreateRecord`` creates core records only (module types refuse it, ADR-0010).
AUTOMATION_COMMANDS = frozenset(
    {
        "CreateRecord",
        "UpdateRecord",
        "SetPsetValues",
        "AddLink",
        "SuggestLink",
        "TransitionWorkflow",
        "PostToFeed",
        "InvokeAction",
        # The correspondence module's escalation of an answered RFI (P1-I6, ADR-0019). A rule may
        # only propose it: the command needs a controller viewer, and a service actor reads as the
        # lowest viewer, so acted by a rule or a mapping it is refused.
        "EscalateTechnical",
    }
)

#: Setting that stops every rule, inbound endpoint, action executor and enricher (FANOUT D11).
KILL_SWITCH_SETTING = "integration.kill_switch"

# --------------------------------------------------------------------------------------------
# Bounds (FANOUT D4 to D8). Bigger inputs are refused with a problem, never truncated.
# --------------------------------------------------------------------------------------------

MAX_MESSAGE_CHARS = 500
MAX_SUMMARY_CHARS = 300
MAX_PROBLEMS = 100

# Inbound endpoints (D4)
INBOUND_DEFAULT_MAX_BODY_BYTES = 256 * 1024
INBOUND_HARD_MAX_BODY_BYTES = 1024 * 1024
INBOUND_TOLERANCE_S = 300
INBOUND_REPLAY_RETENTION_S = 2 * INBOUND_TOLERANCE_S
INBOUND_DEFAULT_RATE_PER_MINUTE = 60
INBOUND_MAX_RATE_PER_MINUTE = 600
INBOUND_GLOBAL_RATE_PER_MINUTE = 1200
INBOUND_MAX_PENDING_PER_ENDPOINT = 1000
INBOUND_MAX_JSON_DEPTH = 32
INBOUND_JWT_ALGORITHMS = ("HS256",)
INBOUND_JWT_MAX_LIFETIME_S = 300
INBOUND_JWT_REQUIRED_CLAIMS = ("iat", "exp", "aud", "jti", "body_sha256")
#: Fixed answers (D4): the same bytes whatever the reason, so no answer is an oracle.
INBOUND_NOT_FOUND_BODY = b'{"error":"not_found"}'
INBOUND_UNAUTHORIZED_BODY = b'{"error":"unauthorized"}'

# Mapping runtime (D5)
MAPPING_LANGUAGE = "jsonata-restricted@1"
MAPPING_MAX_EXPRESSION_CHARS = 8_000
MAPPING_MAX_SECONDS = 2.0
MAPPING_MAX_MEMORY_BYTES = 512 * 1024 * 1024
MAPPING_TIMEBOX_MS = 1_000
MAPPING_MAX_DEPTH = 100
MAPPING_MAX_COMMANDS = 50
MAPPING_MAX_OUTPUT_BYTES = 256 * 1024
#: The only JSONata functions a mapping may call. Everything else (``$eval``, ``$now``, ``$millis``,
#: ``$random``, ``$match``, ``$replace``, ``$sift``, ``$each``, higher-order functions, function
#: definitions, regular expressions, partial application) is refused by ``MappingRuntime.check``.
MAPPING_ALLOWED_FUNCTIONS = frozenset(
    {
        "$string",
        "$number",
        "$boolean",
        "$not",
        "$exists",
        "$type",
        "$length",
        "$lowercase",
        "$uppercase",
        "$trim",
        "$substring",
        "$substringBefore",
        "$substringAfter",
        "$contains",
        "$split",
        "$join",
        "$count",
        "$sum",
        "$max",
        "$min",
        "$average",
        "$append",
        "$distinct",
        "$keys",
        "$lookup",
        "$merge",
        "$round",
        "$floor",
        "$ceil",
        "$abs",
    }
)
#: In a mapped command's ``args``: ``{"$key": "47-1234-W012"}`` or ``{"$key": {"type":
#: "core.Record", "key": "47-1234-W012"}}`` is replaced by that record's id (key resolution, D4).
KEY_REF_MARKER = "$key"

# Rules (D7)
RULE_MAX_CAUSATION_DEPTH = 3
RULE_MAX_RULES_PER_EVENT = 20
RULE_MAX_STEPS = 5
RULE_MAX_COMMANDS_PER_EVENT = 20
RULE_MAX_CONDITION_CHARS = 2_000
RULE_MAX_ARGS_BYTES = 16 * 1024
RULE_BATCH_EVENTS = 200
RULE_DRY_RUN_MAX_EVENTS = 10_000
RULE_DRY_RUN_MAX_FIRINGS = 1_000
#: ``${name}`` placeholders a rule step's string args may use (``string.Template``, never
#: ``str.format``: no attribute access). A bound value longer than ``RULE_MAX_BINDING_CHARS`` makes
#: the step refused, never truncated.
RULE_BINDINGS = frozenset(
    {
        "event_id",
        "event_type",
        "event_actor",
        "event_scope",
        "subject_id",
        "subject_key",
        "subject_title",
        "subject_type",
    }
)
RULE_MAX_BINDING_CHARS = 1_000

# Actions (D8)
ACTION_MAX_TARGETS = 100
ACTION_MAX_PARAMETERS = 32
ACTION_MAX_PARAMETERS_BYTES = 16 * 1024
ACTION_MAX_RESULT_BYTES = 64 * 1024
ACTION_WEBHOOK_TIMEOUT_S = 10.0
ACTION_MAX_ATTEMPTS = 3
#: Entry-point group of the code that a ``job`` action runs (never user code).
ACTION_JOB_ENTRY_POINT = "throughline.action_jobs"

# Enrichment (D6)
ENRICHER_ENTRY_POINT = "throughline.enrichers"
ENRICH_MAX_VALUES = 50
ENRICH_MAX_LINKS = 20
ENRICH_MAX_VALUE_CHARS = 4_000
ENRICH_MAX_LIST_ITEMS = 50
ENRICH_DEFAULT_AUTO_THRESHOLD = 0.9


# --------------------------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------------------------


class Problem(BaseModel):
    """A refusal or a failure: a short fixed code and words for a person (no paths, no traces)."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(max_length=MAX_MESSAGE_CHARS)


class RecordRef(BaseModel):
    """A pointer to a record at a version (§19.2 ``RecordRef``; §19.3: every object carries one)."""

    id: str
    key: str | None = None
    record_type: str
    version: int | None = None
    seq: int | None = None


class PlannedCommand(BaseModel):
    """One command that automation or a dispatch would run, as a preview shows it.

    ``command`` holds the fields of the command model except ``actor`` (which the runner sets).
    ``access`` is what the command needs (``None``: nothing declares it, so it is refused);
    ``permitted`` says whether the actor that would run it holds that access. ``problem`` is set
    when the command would be refused (validation, access, a missing record, a stale state).
    """

    command_type: str
    command: dict[str, Any] = Field(default_factory=dict[str, Any])
    access: Access | None = None
    permitted: bool = False
    summary: str = Field(default="", max_length=MAX_SUMMARY_CHARS)
    problem: Problem | None = None


@runtime_checkable
class CommandRunner(Protocol):
    """The typed command table, injected by an entry point (API, CLI, TUI, worker).

    ``tl_core`` never imports ``tl_api``: an entry point builds a runner from
    ``tl_api.commands.COMMANDS`` (``tl_api.commands.command_runner()``, WS-A builds it in its first
    supervisor piece) and passes it to the rules engine, the inbound worker and the dispatch
    planner. A command type the runner does not know is refused.
    """

    def model_of(self, command_type: str) -> type[Command] | None:
        """The command model of a type, or ``None`` when the table has no such command."""
        ...

    def access_of(self, command_type: str) -> Access | None:
        """What the command needs; ``None`` when nothing declares it (fail closed)."""
        ...

    def run(self, uow: UnitOfWork, command: Command) -> CommandResult:
        """Call the command's ``tl_core`` handler in ``uow``. Raises the handler's errors."""
        ...


#: ``holds(level)`` tells whether the person on whose behalf a client acts has that access. Passed
#: as a Python argument by the client layer, never read from a request body (ADR-0014 section 8).
Holds = Callable[[Access], bool]


# --------------------------------------------------------------------------------------------
# Actions (§18.7, §19.2 ActionDefinition / ActionInvocation)
# --------------------------------------------------------------------------------------------

ExecutorKind = Literal["webhook", "mcp_tool", "connector", "job", "agent"]
#: The executors Phase 1 builds. A definition naming another is refused (``executor_unavailable``).
PHASE1_EXECUTORS: tuple[ExecutorKind, ...] = ("job", "webhook")
SideEffectClass = Literal["read", "propose", "write", "external"]
ResultHandling = Literal["store", "post_to_feed"]
InvocationStatus = Literal["requested", "running", "completed", "failed"]
ParameterKind = Literal["string", "int", "decimal", "bool", "date", "record_ref"]


class ActionParameter(BaseModel):
    """One parameter of an action. A flat list of these replaces §19.2 ``parameters_class`` in
    Phase 1 (FANOUT D8): a form can be generated from it and it holds no regular expression."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    label: str = Field(min_length=1, max_length=200)
    kind: ParameterKind = "string"
    required: bool = False
    max_length: int | None = Field(default=None, ge=1, le=10_000)
    choices: list[str] | None = Field(default=None, max_length=200)


class ActionTarget(BaseModel):
    """``applies_to`` (§18.2): record types (globs) and an optional query-language condition."""

    model_config = ConfigDict(extra="forbid")

    record_types: list[str] = Field(default_factory=lambda: ["*"], min_length=1, max_length=50)
    condition: str | None = Field(default=None, max_length=RULE_MAX_CONDITION_CHARS)


class JobExecutorConfig(BaseModel):
    """Run code registered under :data:`ACTION_JOB_ENTRY_POINT` through the job queue."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["job"] = "job"
    job: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,62}$")


class WebhookExecutorConfig(BaseModel):
    """POST a signed request to ``url``; the response is the result (synchronous, D8).

    ``url`` is checked by the webhook egress policy when the action is defined and again at every
    attempt (DNS pinning, private and loopback ranges refused unless allow-listed). The signing
    secret lives in the operational secret table; ``secret_id`` is set by the server only.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["webhook"] = "webhook"
    url: str = Field(max_length=2_000)
    timeout_s: float = Field(default=ACTION_WEBHOOK_TIMEOUT_S, gt=0, le=ACTION_WEBHOOK_TIMEOUT_S)
    secret_id: str | None = None


class ActionDefinition(BaseModel):
    """§19.2 ``ActionDefinition``. A record of its own stream (``core.ActionDefinition``)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    scope: str
    version: int = Field(default=1, ge=1)
    applies_to: ActionTarget = Field(default_factory=ActionTarget)
    parameters: list[ActionParameter] = Field(
        default_factory=list[ActionParameter], max_length=ACTION_MAX_PARAMETERS
    )
    executor: ExecutorKind
    executor_config: JobExecutorConfig | WebhookExecutorConfig = Field(discriminator="kind")
    side_effect_class: SideEffectClass
    requires_approval: bool = False
    #: §18.7 ``permissions``: who may invoke it.
    access: Access = "user"
    result_handling: list[ResultHandling] = Field(default_factory=lambda: ["store"])
    owner: str
    enabled: bool = True

    @model_validator(mode="after")
    def _executor_matches_config(self) -> ActionDefinition:
        if self.executor not in ("job", "webhook") or self.executor != self.executor_config.kind:
            raise ValueError("executor must be 'job' or 'webhook' and match executor_config.kind")
        return self


class InvokeAction(Command):
    """Ask for an action on records. The handler checks the definition's ``access`` with ``holds``
    (client layer), its ``applies_to`` and its parameters, then appends ``Action.Requested`` on a
    new ``core.ActionInvocation`` stream and queues the execution."""

    action: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    targets: list[str] = Field(default_factory=list[str], max_length=ACTION_MAX_TARGETS)
    parameters: dict[str, Any] = Field(default_factory=dict[str, Any])


class ActionRequest(BaseModel):
    """What an executor is told. No secret: the webhook executor reads its secret by ``secret_id``
    from the operational table itself, inside the attempt."""

    invocation_id: str
    action: str
    action_version: int
    scope: str
    targets: list[RecordRef] = Field(default_factory=list[RecordRef])
    parameters: dict[str, Any] = Field(default_factory=dict[str, Any])
    invoked_by: str
    attempt: int = Field(ge=1)
    config: JobExecutorConfig | WebhookExecutorConfig = Field(discriminator="kind")


class ActionOutcome(BaseModel):
    """What an executor returns. ``result`` is JSON and at most :data:`ACTION_MAX_RESULT_BYTES`
    as canonical JSON; the service refuses a larger one (failed, never truncated)."""

    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    http_status: int | None = None
    retryable: bool = False
    problems: list[Problem] = Field(default_factory=list[Problem], max_length=MAX_PROBLEMS)
    notes: list[str] = Field(default_factory=list[str], max_length=20)

    @model_validator(mode="after")
    def _failed_says_why(self) -> ActionOutcome:
        if self.status == "failed" and not self.problems:
            raise ValueError("a failed outcome names at least one problem")
        return self


@runtime_checkable
class ActionExecutor(Protocol):
    """Performs an action. Never raises for a bad request or a bad answer: that is ``failed``.

    ``job``: calls the :class:`ActionJob` named by the config; pure, no network. ``webhook``: one
    HTTP request through the egress-checked transport of ``tl_core.webhooks`` (no redirects, a
    bounded response); in tests only a stub transport or the loopback dev receiver, never a socket
    off the machine.
    """

    kind: ExecutorKind

    def execute(self, request: ActionRequest) -> ActionOutcome: ...


@runtime_checkable
class ActionJob(Protocol):
    """Code a ``job`` action runs, registered under :data:`ACTION_JOB_ENTRY_POINT`. Pure: no ledger,
    no unit of work, no network, no secrets. Its result is stored on the invocation."""

    name: str
    version: str
    side_effect_class: SideEffectClass

    def run(self, request: ActionRequest) -> ActionOutcome: ...


# --------------------------------------------------------------------------------------------
# Rules (§18.8)
# --------------------------------------------------------------------------------------------

RuleMode = Literal["act", "propose"]
FiringOutcome = Literal[
    "fired", "proposed", "skipped_condition", "refused", "depth_limit", "budget", "killed"
]


class RuleStep(BaseModel):
    """One *then*: a command from the rule's allow-list with static args. String values may hold
    ``${binding}`` placeholders from :data:`RULE_BINDINGS`."""

    model_config = ConfigDict(extra="forbid")

    command: str
    args: dict[str, Any] = Field(default_factory=dict[str, Any])

    @field_validator("command")
    @classmethod
    def _allowed(cls, value: str) -> str:
        if value not in AUTOMATION_COMMANDS:
            raise ValueError(f"{value!r} is not a command automation may run")
        return value

    @field_validator("args")
    @classmethod
    def _no_server_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        named = sorted(SERVER_SET_FIELDS & set(value))
        if named:
            raise ValueError(f"the server sets {', '.join(named)}")
        return value


class Rule(BaseModel):
    """§18.8 rule. A record of its own stream (``core.Rule``); every change is a new version."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    title: str = Field(min_length=1, max_length=200)
    scope: str
    version: int = Field(default=1, ge=1)
    #: *When*: a ``SubscriptionFilter`` as JSON (``tl_core.webhooks.filters.WebhookFilter``).
    when: dict[str, Any]
    #: *If*: a query-language expression the subject record must match; ``None`` always matches.
    condition: str | None = Field(default=None, max_length=RULE_MAX_CONDITION_CHARS)
    #: *Then*.
    then: list[RuleStep] = Field(min_length=1, max_length=RULE_MAX_STEPS)
    mode: RuleMode = "propose"
    service_actor: str
    access: AutomationAccess = "user"
    owner: str
    enabled: bool = False

    @field_validator("service_actor")
    @classmethod
    def _service_actor(cls, value: str) -> str:
        if SERVICE_ACTOR_RE.fullmatch(value) is None or not value.startswith("svc:rule-"):
            raise ValueError("service_actor must be svc:rule-<slug>")
        return value


class RuleFiring(BaseModel):
    """What one rule did, or would do in a dry run, for one event."""

    rule: str
    rule_version: int
    event_id: str
    seq: int
    depth: int = Field(ge=0)
    outcome: FiringOutcome
    #: Dry runs evaluate the condition on the record as it is now, not as of the event (D7).
    condition_basis: Literal["current", "as_of_event"] = "current"
    planned: list[PlannedCommand] = Field(default_factory=list[PlannedCommand])
    problems: list[Problem] = Field(default_factory=list[Problem], max_length=MAX_PROBLEMS)


# --------------------------------------------------------------------------------------------
# Inbound endpoints and the mapping runtime (§18.5, §19.3)
# --------------------------------------------------------------------------------------------

InboundAuth = Literal["hmac_sha256", "jwt_hs256"]
MappingStatus = Literal["ok", "invalid_output", "limit", "error"]


class InboundEndpoint(BaseModel):
    """``POST /in/{app}/{name}``. A record of its own stream (``core.InboundEndpoint``). Its secrets
    live in the operational secret table; events carry ``current_secret_id`` only."""

    model_config = ConfigDict(extra="forbid")

    app: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    scope: str
    version: int = Field(default=1, ge=1)
    auth: InboundAuth = "hmac_sha256"
    mapping: str = Field(min_length=1, max_length=MAPPING_MAX_EXPRESSION_CHARS)
    mapping_language: Literal["jsonata-restricted@1"] = "jsonata-restricted@1"
    #: §19.3: which external schema the mapping reads (a name and version, or a URL).
    external_schema: str | None = Field(default=None, max_length=500)
    allowed_commands: list[str] = Field(min_length=1, max_length=len(AUTOMATION_COMMANDS))
    service_actor: str
    access: AutomationAccess = "user"
    max_body_bytes: int = Field(
        default=INBOUND_DEFAULT_MAX_BODY_BYTES, ge=1, le=INBOUND_HARD_MAX_BODY_BYTES
    )
    rate_per_minute: int = Field(
        default=INBOUND_DEFAULT_RATE_PER_MINUTE, ge=1, le=INBOUND_MAX_RATE_PER_MINUTE
    )
    #: Verify, map and plan every delivery; never run a command.
    dry_run: bool = True
    enabled: bool = False
    current_secret_id: str | None = None
    owner: str

    @field_validator("allowed_commands")
    @classmethod
    def _subset(cls, value: list[str]) -> list[str]:
        extra = sorted(set(value) - AUTOMATION_COMMANDS)
        if extra:
            raise ValueError(f"not commands automation may run: {', '.join(extra)}")
        return value

    @field_validator("service_actor")
    @classmethod
    def _service_actor(cls, value: str) -> str:
        if SERVICE_ACTOR_RE.fullmatch(value) is None or not value.startswith("svc:inbound-"):
            raise ValueError("service_actor must be svc:inbound-<slug>")
        return value


def _names_server_field(value: Any, depth: int = 0) -> str | None:
    """The first server-set field name found as a key anywhere in ``value`` (bounded walk)."""
    if depth > INBOUND_MAX_JSON_DEPTH:
        return "<too deep>"
    if isinstance(value, dict):
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            if key in SERVER_SET_FIELDS:
                return str(key)  # pyright: ignore[reportUnknownArgumentType]
            found = _names_server_field(item, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            found = _names_server_field(item, depth + 1)
            if found is not None:
                return found
    return None


class MappedCommand(BaseModel):
    """One element of a mapping's output: ``{"command": "<Name>", "args": {...}}``.

    ``args`` never name a server-set field at any depth; ``{"$key": ...}`` objects are resolved to
    record ids before the command model is built. The endpoint's allow-list is checked by the
    worker (this model checks only the global :data:`AUTOMATION_COMMANDS`).
    """

    model_config = ConfigDict(extra="forbid")

    command: str
    args: dict[str, Any] = Field(default_factory=dict[str, Any])

    @field_validator("command")
    @classmethod
    def _allowed(cls, value: str) -> str:
        if value not in AUTOMATION_COMMANDS:
            raise ValueError(f"{value!r} is not a command automation may run")
        return value

    @field_validator("args")
    @classmethod
    def _no_server_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        found = _names_server_field(value)
        if found is not None:
            raise ValueError(f"the server sets {found}")
        return value


class MappingOutcome(BaseModel):
    """What a mapping evaluation returns. ``limit``: the time, depth or memory bound was hit, or
    the output was too large. ``invalid_output``: the result is not a list of mapped commands."""

    status: MappingStatus
    commands: list[MappedCommand] = Field(
        default_factory=list[MappedCommand], max_length=MAPPING_MAX_COMMANDS
    )
    problems: list[Problem] = Field(default_factory=list[Problem], max_length=MAX_PROBLEMS)

    @model_validator(mode="after")
    def _consistent(self) -> MappingOutcome:
        if self.status != "ok" and not self.problems:
            raise ValueError("an outcome that is not ok names at least one problem")
        if self.status != "ok" and self.commands:
            raise ValueError("an outcome that is not ok carries no commands")
        return self


@runtime_checkable
class MappingRuntime(Protocol):
    """The restricted JSONata runtime (FANOUT D5). Pure; never raises for bad input.

    ``check`` parses an expression and walks it against the restricted profile (allowed functions,
    no function definitions, no regular expressions, no partial application, the length bound) and
    returns the problems; an empty list means the expression may be stored. ``evaluate`` runs it
    over ``payload`` in a separate process under :data:`MAPPING_MAX_SECONDS` and
    :data:`MAPPING_MAX_MEMORY_BYTES` (the ADR-0014 envelope) with the library's own time box
    (:data:`MAPPING_TIMEBOX_MS`, :data:`MAPPING_MAX_DEPTH`) inside; no network, no filesystem.
    The output must be a list (or a single object) of mapped commands of at most
    :data:`MAPPING_MAX_OUTPUT_BYTES` as JSON.
    """

    language: str

    def check(self, expression: str) -> list[Problem]: ...

    def evaluate(self, expression: str, payload: Any) -> MappingOutcome: ...


# --------------------------------------------------------------------------------------------
# Enrichment (§18.9, §19.2 EnrichmentValue)
# --------------------------------------------------------------------------------------------

AcceptancePolicy = Literal["auto", "propose", "shadow"]
AcceptanceState = Literal["shadow", "proposed", "accepted", "auto_accepted", "rejected"]
EnrichmentStatus = Literal["ok", "unsupported", "failed"]
Scalar = str | int | float | bool | None
EnrichedValue = Scalar | list[Scalar]


class EnrichmentFile(BaseModel):
    """The file facts an enricher may read (from the file service and the derivation metadata)."""

    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None = None
    title: str | None = None
    author: str | None = None


class EnrichmentSubject(BaseModel):
    """What an enricher is told about one record. Read-only; no connection, no secret."""

    record: RecordRef
    title: str
    status: str | None = None
    psets: dict[str, Any] = Field(default_factory=dict[str, Any])
    file: EnrichmentFile | None = None


class ProposedValue(BaseModel):
    """A value for ``property`` of the enricher's own layer ``enrich.<enricher>``."""

    property: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    value: EnrichedValue
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def _bounded(cls, value: EnrichedValue) -> EnrichedValue:
        items: list[Scalar] = value if isinstance(value, list) else [value]
        if len(items) > ENRICH_MAX_LIST_ITEMS:
            raise ValueError(f"at most {ENRICH_MAX_LIST_ITEMS} items")
        for item in items:
            if isinstance(item, str) and len(item) > ENRICH_MAX_VALUE_CHARS:
                raise ValueError(f"a text value is at most {ENRICH_MAX_VALUE_CHARS} characters")
        return value


class ProposedLink(BaseModel):
    """A link the enricher suggests from the subject to another record (link source ``enricher``,
    always a suggestion a person accepts or declines)."""

    to_key: str = Field(min_length=1, max_length=255)
    relation: str = Field(default="references", pattern=r"^[a-z][a-z0-9_]*$")
    confidence: float = Field(ge=0.0, le=1.0)


class EnrichmentResult(BaseModel):
    """What an enricher returns for one subject."""

    enricher: str
    enricher_version: str
    status: EnrichmentStatus
    values: list[ProposedValue] = Field(
        default_factory=list[ProposedValue], max_length=ENRICH_MAX_VALUES
    )
    links: list[ProposedLink] = Field(
        default_factory=list[ProposedLink], max_length=ENRICH_MAX_LINKS
    )
    problems: list[Problem] = Field(default_factory=list[Problem], max_length=MAX_PROBLEMS)
    #: e.g. "deterministic classifier, no model (ADR-0008 decision 8)".
    notes: list[str] = Field(default_factory=list[str], max_length=20)


class EnrichmentInput(BaseModel):
    """§18.9 provenance ``inputs``: the record version and the file hash the value was made from."""

    record: RecordRef
    file_sha256: str | None = None


class EnrichmentValue(BaseModel):
    """§19.2 ``EnrichmentValue``: what the service stores for one proposed value, with provenance.

    ``property_path`` is ``enrich.<enricher>.<property>``; the service never writes outside that
    layer, and accepting a value writes only there. Promoting it to an authoritative field is a
    person's own ``SetPsetValues``.
    """

    value_id: str
    target: RecordRef
    property_path: str
    value: EnrichedValue
    enricher: str
    enricher_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    inputs: list[EnrichmentInput] = Field(min_length=1)
    #: Model and prompt hash for an AI enricher; ``None`` for a deterministic one (ADR-0008).
    model_ref: str | None = None
    produced_at: str
    acceptance_state: AcceptanceState

    @model_validator(mode="after")
    def _namespaced(self) -> EnrichmentValue:
        prefix = f"{ENRICHMENT_PSET_PREFIX}{self.enricher}."
        rest = self.property_path.removeprefix(prefix)
        if (
            ENRICHER_NAME_RE.fullmatch(self.enricher) is None
            or not self.property_path.startswith(prefix)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,62}", rest) is None
        ):
            raise ValueError(f"property_path must be {prefix}<property>")
        return self


@runtime_checkable
class Enricher(Protocol):
    """A plugin registered under :data:`ENRICHER_ENTRY_POINT`. Pure: no ledger, no network, no
    secret, no global state; never raises for a bad subject (that is ``failed``)."""

    name: str
    version: str
    #: ``None`` for a deterministic enricher. Phase 1 refuses an enricher whose ``model_ref`` is
    #: set (ADR-0008 decision 8: no model call, no spend).
    model_ref: str | None

    def accepts(self, subject: EnrichmentSubject) -> bool: ...

    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult: ...
