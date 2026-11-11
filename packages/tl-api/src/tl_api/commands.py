"""``POST /commands/{CommandName}``: the shared command models as HTTP (brief 11.1, O5).

One table lists the commands; one route per row is generated from it. A route's body is the
command model without ``actor`` (it comes from the token, never from the body: a body that carries
``actor`` is a 422) and with ``source`` optional (default ``api``). The route builds the real
command model, which runs its own validators, opens a unit of work, calls the tl_core handler and
returns its ``CommandResult``. There is no business rule in this module.

This module does not use ``from __future__ import annotations``: FastAPI reads the generated
endpoints' annotations at run time, and one of them closes over a local (the action name).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import (
    command_index,
    holder_for_principal,
    normalise_word,
    require_command_access,
)
from tl_core.auth.types import Principal
from tl_core.confidentiality import viewer_for
from tl_core.constraints.commands import command_table as constraint_commands
from tl_core.integration.actions.service import (
    RetireAction,
    ReviseAction,
    handle_invoke_action,
    handle_retire_action,
    handle_revise_action,
)
from tl_core.integration.actor_access import holds_for, require_access, workflow_roles_of
from tl_core.integration.apps import (
    RegisterIntegrationApp,
    ReviseIntegrationApp,
    SetIntegrationAppEnabled,
    handle_register_app,
    handle_revise_app,
    handle_set_app_enabled,
)
from tl_core.integration.contract import Access as Access_
from tl_core.integration.contract import InvokeAction
from tl_core.integration.enrichers.commands import (
    AcceptEnrichment,
    RejectEnrichment,
    RunEnricher,
    handle_accept_enrichment,
    handle_reject_enrichment,
    handle_run_enricher,
)
from tl_core.integration.enrichers.service import (
    RegisterEnricher,
    ReviseEnricher,
    SetEnricherEnabled,
    handle_register_enricher,
    handle_revise_enricher,
    handle_set_enricher_enabled,
)
from tl_core.integration.errors import CommandAccessError
from tl_core.integration.inbound.delivery import RetryInboundDelivery, handle_retry_delivery
from tl_core.integration.inbound.service import (
    ReviseInboundEndpoint,
    SetInboundEndpointEnabled,
    handle_revise_endpoint,
    handle_set_endpoint_enabled,
)
from tl_core.integration.rules.service import (
    CreateRule,
    DisableRule,
    EnableRule,
    ReviseRule,
    handle_create_rule,
    handle_disable_rule,
    handle_enable_rule,
    handle_revise_rule,
)
from tl_core.intent import check_intent, intent_scope, register_command_names
from tl_core.services import links, psets
from tl_core.services.commands import Command, CommandResult, CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord, handle_edit_record
from tl_core.services.feed import EditPost, PostToFeed, handle_edit_post, handle_post
from tl_core.services.feed_actions import (
    ReactToPost,
    RetractPost,
    handle_react_to_post,
    handle_retract_post,
)
from tl_core.services.proposals import source_for
from tl_core.services.records import handle_create_record, handle_update_record
from tl_core.services.reserved import refuse_reserved, refuse_reserved_fields, refuse_role_claim
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.threads import messages as thread_messages
from tl_core.uow import UnitOfWork
from tl_core.util import effective_time
from tl_core.workflow.roles import workflow_roles
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_correspondence.commands import API_COMMANDS as CORRESPONDENCE_COMMANDS
from tl_mod_cost.commands import API_COMMANDS as COST_COMMANDS
from tl_mod_documents.commands import API_COMMANDS as DOCUMENT_COMMANDS
from tl_mod_engineering.commands import API_COMMANDS
from tl_mod_materials.commands import MATERIALS_COMMANDS
from tl_mod_quality.module import PUNCH_COMMANDS
from tl_mod_schedule.commands import API_COMMANDS as SCHEDULE_COMMANDS
from tl_mod_schemareg.commands import API_COMMANDS as SCHEMAREG_COMMANDS

from tl_api.auth import AGENT_DIRECT_COMMANDS, current_principal, guard
from tl_api.context import ApiContext, get_ctx
from tl_api.effective import EFFECTIVE_AT_HEADER, resolve_effective_at

Handler = Callable[[UnitOfWork, Any], CommandResult]
#: The four words a command table has always used, or a fine word (``awp.cwp.release``) that
#: ``schema/settings/access-words.yaml`` maps to a table word. Any other string is refused when the
#: ``CommandSpec`` is built (``AccessWordError``): a typo is a start-up error, not an open door.
Access = Literal["admin", "controller", "company", "user"] | str
SOURCE_PATTERN = r"^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]+)?$"
DEFAULT_SOURCE = "api"
CONTROLLER_PREFIX = "control.command."
#: Core commands (no module) that may be ``controller`` commands. A ``controller`` command with
#: ``module=None`` and a name not listed here is a start-up error: there would be no module whose
#: role table could decide it. There are none today (every ``controller`` command is a module's).
CORE_CONTROLLER_COMMANDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CommandSpec:
    model: type[Command]
    handler: Handler
    #: "user": any signed-in person; "admin": only an admin (action ``admin.command.<Name>``);
    #: "controller": an admin or a document controller (action ``control.command.<Name>``,
    #: ADR-0013); "company": an admin when ``scope`` is ``company``, any signed-in person otherwise.
    access: Access = "user"
    #: The handler takes ``holds(level)`` (a Python argument made from the caller's principal,
    #: never a field of the body) because its access depends on the content of the command
    #: (``InvokeAction``: the access of the action named, ADR-0014 section 8).
    needs_holds: bool = False
    #: The handler also takes ``roles=``: the caller's workflow roles, derived here from the
    #: authenticated principal (``tl_core.workflow.roles``) and never read from the body.
    takes_roles: bool = False
    #: The module whose role table decides this command (``tl_core.auth.module_roles``): the name
    #: in ``ModuleSpec.name``. ``None`` for a core command.
    module: str | None = None

    def __post_init__(self) -> None:
        word = normalise_word(self.access)  # AccessWordError for a typo: a start-up failure
        core_controller = self.module is None and self.name not in CORE_CONTROLLER_COMMANDS
        if word == "controller" and core_controller:
            raise ValueError(
                f"{self.name} is a controller command with no module: "
                "nothing could say who holds the word"
            )

    @property
    def name(self) -> str:
        return self.model.__name__


def effective_access(spec: CommandSpec) -> str:
    """The access of a command as a table word or a platform word: a fine word is read here, as
    its table word (``command_index()`` reads it the same way, from the module's declaration)."""
    return normalise_word(spec.access)


def _module_specs(module: str, commands: Iterable[Any]) -> tuple[CommandSpec, ...]:
    """The ``CommandSpec`` rows of a module's ``API_COMMANDS``, each carrying its module name."""
    return tuple(CommandSpec(c.model, c.handler, c.access, module=module) for c in commands)


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(CreateRecord, handle_create_record),
    CommandSpec(UpdateRecord, handle_update_record),
    CommandSpec(EditRecord, handle_edit_record),
    CommandSpec(psets.SetPsetValues, psets.handle_set_pset_values),
    CommandSpec(links.AddLink, links.handle_add_link),
    CommandSpec(links.SuggestLink, links.handle_suggest_link),
    CommandSpec(links.AcceptLink, links.handle_accept_link),
    CommandSpec(links.DeclineLink, links.handle_decline_link),
    CommandSpec(links.RepinLink, links.handle_repin_link),
    CommandSpec(links.VerifyLink, links.handle_verify_link),
    CommandSpec(links.FlagLink, links.handle_flag_link),
    CommandSpec(links.RetractLink, links.handle_retract_link),
    # recovery: any link, whatever its source or owner (ADR-0011)
    CommandSpec(links.AdminFlagLink, links.handle_admin_flag_link, "admin"),
    CommandSpec(links.AdminRetractLink, links.handle_admin_retract_link, "admin"),
    CommandSpec(TransitionWorkflow, handle_transition_workflow, takes_roles=True),
    CommandSpec(PostToFeed, handle_post),
    CommandSpec(EditPost, handle_edit_post),
    CommandSpec(RetractPost, handle_retract_post),
    CommandSpec(ReactToPost, handle_react_to_post),
    CommandSpec(ChangeSetting, handle_change_setting),
    *_module_specs("engineering", API_COMMANDS),
    *_module_specs("documents", DOCUMENT_COMMANDS),
    # P1-I7 WS-B: record threads. A message changes no record and never dispatches (D9).
    CommandSpec(thread_messages.PostThreadMessage, thread_messages.handle_post_thread_message),
    CommandSpec(thread_messages.EditThreadMessage, thread_messages.handle_edit_thread_message),
    CommandSpec(
        thread_messages.RetractThreadMessage, thread_messages.handle_retract_thread_message
    ),
    # P1-I7 WS-A: the integration layer. Authoring is the admin's (FANOUT D12).
    CommandSpec(CreateRule, handle_create_rule, "admin"),
    CommandSpec(ReviseRule, handle_revise_rule, "admin"),
    CommandSpec(EnableRule, handle_enable_rule, "admin"),
    CommandSpec(DisableRule, handle_disable_rule, "admin"),
    CommandSpec(InvokeAction, handle_invoke_action, needs_holds=True),
    CommandSpec(ReviseAction, handle_revise_action, "admin"),
    CommandSpec(RetireAction, handle_retire_action, "admin"),
    CommandSpec(RegisterIntegrationApp, handle_register_app, "admin"),
    CommandSpec(ReviseIntegrationApp, handle_revise_app, "admin"),
    CommandSpec(SetIntegrationAppEnabled, handle_set_app_enabled, "admin"),
    CommandSpec(ReviseInboundEndpoint, handle_revise_endpoint, "admin"),
    CommandSpec(SetInboundEndpointEnabled, handle_set_endpoint_enabled, "admin"),
    CommandSpec(RetryInboundDelivery, handle_retry_delivery, "admin"),
    CommandSpec(RegisterEnricher, handle_register_enricher, "admin"),
    CommandSpec(ReviseEnricher, handle_revise_enricher, "admin"),
    CommandSpec(SetEnricherEnabled, handle_set_enricher_enabled, "admin"),
    # a person runs an enricher on a record, accepts or rejects a value (the target type decides)
    CommandSpec(RunEnricher, handle_run_enricher),
    CommandSpec(AcceptEnrichment, handle_accept_enrichment),
    CommandSpec(RejectEnrichment, handle_reject_enrichment),
    *_module_specs("correspondence", CORRESPONDENCE_COMMANDS),
    # ADR-0024: core constraints; the word core.constraint.edit is also checked by the handler
    *(CommandSpec(c.model, c.handler, c.access) for c in constraint_commands()),
    *_module_specs("awp", AWP_COMMANDS),
    *_module_specs("cost", COST_COMMANDS),
    *_module_specs("materials", MATERIALS_COMMANDS),
    *_module_specs("quality", PUNCH_COMMANDS),
    *_module_specs("schedule", SCHEDULE_COMMANDS),
    *_module_specs("schemareg", SCHEMAREG_COMMANDS),
)
"""Every command the API accepts. Void, mark-pins-stale and the file commands are not here:
voiding is not in the Phase 0 client contract, pin staleness is a system command, and files have
their own upload routes."""


COMMAND_BODIES: dict[str, type[BaseModel]] = {}
"""Every body model ``request_model`` made, by name: a test walks the routes against it."""


def request_model(model: type[Command], name: str) -> type[BaseModel]:
    """The body model for a command: its fields minus ``actor``, ``source`` made optional.

    Unknown fields (``actor`` included) are refused, and so is a reserved ``source``,
    ``correlation_id`` or ``causation_id`` (ADR-0014) and a claim of workflow roles
    (``actor_roles``, ADR-0013 addendum P1-SEC1). Used for the commands here and for the
    upload commands in ``routes/files.py``.
    """
    fields: dict[str, Any] = {}
    for field_name, info in model.model_fields.items():
        if field_name == "actor":
            continue
        if field_name == "source":
            fields[field_name] = (str, Field(default=DEFAULT_SOURCE, pattern=SOURCE_PATTERN))
        else:
            fields[field_name] = (info.annotation, info)
    body = create_model(
        f"{name}Body",
        __config__=ConfigDict(extra="forbid"),
        __validators__=cast(
            Any, {"refuse_reserved": model_validator(mode="before")(_refuse_reserved_body)}
        ),
        **fields,
    )
    COMMAND_BODIES[body.__name__] = body  # the walking test's key
    return body


def _refuse_reserved_body(data: Any) -> Any:
    """Every client body is checked here, once, before any field is: a route cannot forget it.

    The error is the service's ``ReservedIdentifierError`` (not a validation error), so the client
    sees the same 422 ``reserved_identifier`` from every route that takes a command body, the
    upload routes included (ADR-0014; security re-review of b5f5d41). A body that names workflow
    roles gets the same treatment, 422 ``role_claim_refused``: the roles of a guard are derived
    from the signed-in account, so no route takes them from a client (ADR-0013 addendum P1-SEC1).
    """
    if isinstance(data, dict):
        body = cast(dict[str, Any], data)
        refuse_role_claim(body)
        refuse_reserved_fields(
            source=body.get("source"),
            correlation_id=body.get("correlation_id"),
            causation_id=body.get("causation_id"),
        )
    return data


def action_for(spec: CommandSpec) -> str:
    """The authorization action of a command: one explicit prefix per access level."""
    access = effective_access(spec)
    if access == "admin":
        return f"admin.command.{spec.name}"
    if access == "controller":
        return f"{CONTROLLER_PREFIX}{spec.name}"
    if access in ("company", "user", "read"):
        return f"command.{spec.name}"
    raise ValueError(f"unknown access {spec.access!r} for {spec.name}")  # fail closed at start-up


def controller_actions() -> frozenset[str]:
    """The exact ``control.command.<Name>`` actions of the module commands that need the
    ``controller`` word (ADR-0013, ADR-0021)."""
    return frozenset(
        action_for(spec) for spec in COMMANDS if effective_access(spec) == "controller"
    )


def command_spec(name: str) -> CommandSpec | None:
    """The ``COMMANDS`` row named ``name``, or ``None`` for a name the table does not carry."""
    return next((spec for spec in COMMANDS if spec.name == name), None)


register_command_names(spec.name for spec in COMMANDS)


def run_command(
    ctx: ApiContext,
    spec: CommandSpec,
    command: Command,
    *,
    principal: Principal,
    effective_at: str | None = None,
    path: str = "",
    guard: bool = True,
) -> CommandResult:
    """Everything a command endpoint does once the model is built, once, for every caller.

    The JSON endpoints and the web action route both call this, so the reserved-field refusal, the
    company-admin check, the effective time and the module-role access check (ADR-0021) have no
    second copy. ``path`` is the resource named in an admin refusal (the request path). A refusal is
    raised (``ForbiddenError``, ``CommandAccessError``, ...) before the handler runs.

    ``guard`` (the default, fail closed) runs the endpoint guard's two calls first (the role
    authorizer, then the legacy ``ctx.authorize`` hook, for ``action_for(spec)`` on ``path``), so a
    caller with no ``guard`` dependency (the web action route) is held to the same check as the JSON
    endpoint. The JSON endpoints pass ``guard=False``: their ``guard`` dependency already ran both,
    before the body was read.
    """
    actor = command.actor
    if guard:
        action = action_for(spec)
        ctx.authorizer.authorize(principal, action, path)
        ctx.authorize(principal.actor, action, path)
    refuse_reserved(command)  # a client cannot pose as a publication (ADR-0014)
    if effective_access(spec) == "company" and command.scope == "company":
        ctx.authorizer.authorize(principal, f"admin.command.{spec.name}", path)
    when = resolve_effective_at(effective_at, command.scope)
    with effective_time(when), ctx.backend(False) as uow:
        # the one access function (ADR-0021): the module role table decides, for this project
        require_command_access(uow.conn(), command, holder=holder_for_principal(principal))
        # after the access decision, so an intent never changes it; a bad intent refuses the whole
        # command before the handler runs (ADR-0025 d4)
        command = check_intent(command, uow.conn(), viewer_for(principal))
        with intent_scope(command.intent):
            if spec.needs_holds:
                from tl_api.routes.proposals import holds_access

                return cast(Any, spec.handler)(
                    uow, command, holds=lambda level: holds_access(principal, actor, level)
                )
            if spec.takes_roles:
                return cast(Any, spec.handler)(uow, command, roles=workflow_roles(principal))
            return spec.handler(uow, command)


def _make_endpoint(spec: CommandSpec, body_model: type[BaseModel]) -> Callable[..., CommandResult]:
    action = action_for(spec)
    changes_records = spec.name not in AGENT_DIRECT_COMMANDS

    def endpoint(
        request: Request,
        body: Any,
        actor: Annotated[str, Depends(guard(action, changes_records=changes_records))],
        principal: Annotated[Principal, Depends(current_principal)],
        effective_at: Annotated[
            str | None,
            Header(
                alias=EFFECTIVE_AT_HEADER,
                description="Simulated time (ISO-8601 with offset) stamped as the events' "
                "effective_at. Accepted only for simulation scopes `project:sim-<run>`; any other "
                "scope is a 400 `effective_time_forbidden`.",
            ),
        ] = None,
    ) -> CommandResult:
        ctx = get_ctx(request)
        fields = body.model_dump()
        if actor.startswith("agent:"):  # an agent cannot claim another source (brief 18.12)
            fields["source"] = source_for(actor)
        command = spec.model(**fields, actor=actor)
        return run_command(
            ctx, spec, command, principal=principal, effective_at=effective_at,
            path=request.url.path, guard=False,  # the guard dependency already ran both calls
        )  # fmt: skip

    endpoint.__name__ = f"command_{spec.name}"
    endpoint.__doc__ = (spec.model.__doc__ or "").strip() or f"Run the {spec.name} command."
    endpoint.__annotations__["body"] = body_model
    return endpoint


def check_command_words(specs: Iterable[CommandSpec] = COMMANDS) -> None:
    """Every module command's row agrees with the module's ``command_words`` (fail closed).

    ``require_command_access`` reads ``command_index()``, the route reads the row: a command the
    index does not list would pass the module check unseen, and a word that differs would be
    decided differently on two paths. Either is a start-up error.
    """
    index = command_index()
    for spec in specs:
        if spec.module is None:
            continue
        found = index.get(spec.name)
        if found != (spec.module, effective_access(spec)):
            raise ValueError(
                f"{spec.name}: the command table says {(spec.module, effective_access(spec))!r}, "
                f"the module's command_words say {found!r}"
            )


def build_router() -> APIRouter:
    check_command_words()
    router = APIRouter(tags=["commands"])
    for spec in COMMANDS:
        router.add_api_route(
            f"/commands/{spec.name}",
            _make_endpoint(spec, request_model(spec.model, spec.name)),
            methods=["POST"],
            response_model=CommandResult,
            operation_id=f"command_{spec.name}",
            summary=spec.name,
        )
    return router


router = build_router()


# P1-I7 WS-A: the command runner (FANOUT D14)


class TableCommandRunner:
    """``CommandRunner`` (``tl_core.integration.contract``) over a typed command table.

    ``tl_core`` never imports ``tl_api``: an entry point builds this from ``COMMANDS`` and passes
    it to the rules worker, the inbound worker and the dispatch planner. A name the table does not
    list is unknown (``model_of`` and ``access_of`` answer ``None``, ``run`` raises ``KeyError``),
    so a command nobody declared is refused rather than guessed.
    """

    def __init__(self, specs: tuple[CommandSpec, ...] = COMMANDS) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def model_of(self, command_type: str) -> type[Command] | None:
        spec = self._specs.get(command_type)
        return None if spec is None else spec.model

    def access_of(self, command_type: str) -> Literal["user", "controller", "admin"] | None:
        """What the command needs. ``company`` (an admin when the scope is the company) counts as
        ``admin``: automation never runs it, and failing closed is the safe reading."""
        spec = self._specs.get(command_type)
        if spec is None:
            return None
        access = effective_access(spec)
        if access == "company":
            return "admin"
        if access in ("controller", "admin"):
            return cast(Access_, access)
        return "user"

    def run(self, uow: UnitOfWork, command: Command) -> CommandResult:
        """Run ``command`` only if its own actor holds the access the table declares for it.

        The actor's access is resolved from the ledger in ``uow`` (``tl_core.integration.
        actor_access``), never from the caller, and the check fails closed: an unknown actor, a
        disabled account or a service actor with no live owner holds nothing. A handler that takes
        ``holds`` gets it from the same resolved access. A module command run for a person or an
        agent is decided by the module role table (``require_command_access``) for the command's
        scope; a service actor keeps the access its rule, endpoint or enricher declared.
        """
        spec = self._specs[type(command).__name__]
        if command.actor.startswith("agent:") and spec.name not in AGENT_DIRECT_COMMANDS:
            # an agent proposes record changes (brief 18.12); the runner is not a way around it
            raise CommandAccessError(f"{spec.name}: an agent proposes, a person decides")
        needed: Access_ = "user"
        access = effective_access(spec)
        if access == "admin" or access == "controller":
            needed = access
        elif access == "company" and command.scope == "company":
            needed = "admin"
        held: Access_ | None = None
        if not command.actor.startswith("svc:") and spec.name in command_index():
            # a person's (or agent's) module command: the module role table decides, for this scope
            try:
                require_command_access(uow.conn(), command, dev_file=False)
            except ForbiddenError as exc:  # the runner's callers know one refusal: this one
                raise CommandAccessError(str(exc)) from exc
        else:  # a core command, or automation (a service actor keeps its declared access)
            held = require_access(uow.conn(), command.actor, needed, spec.name)
        if spec.needs_holds:
            if held is None:  # no module command takes ``holds`` today; fail closed if one does
                raise CommandAccessError(f"{spec.name}: its access depends on its content")
            return cast(Any, spec.handler)(uow, command, holds=holds_for(held))
        if spec.takes_roles:
            # the roles of the command's own actor, from the ledger: a person's account, nothing
            # for a service actor (a workflow guard on a role fails closed for automation)
            roles = workflow_roles_of(uow.conn(), command.actor)
            return cast(Any, spec.handler)(uow, command, roles=roles)
        return spec.handler(uow, command)


def command_runner() -> TableCommandRunner:
    """The runner entry points pass to the rules worker, the inbound worker and the planner."""
    return TableCommandRunner()
