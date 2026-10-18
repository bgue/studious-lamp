"""``POST /commands/{CommandName}``: the shared command models as HTTP (brief 11.1, O5).

One table lists the commands; one route per row is generated from it. A route's body is the
command model without ``actor`` (it comes from the token, never from the body: a body that carries
``actor`` is a 422) and with ``source`` optional (default ``api``). The route builds the real
command model, which runs its own validators, opens a unit of work, calls the tl_core handler and
returns its ``CommandResult``. There is no business rule in this module.

This module does not use ``from __future__ import annotations``: FastAPI reads the generated
endpoints' annotations at run time, and one of them closes over a local (the action name).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from tl_core.auth.types import Principal
from tl_core.integration.actions.service import (
    RetireAction,
    ReviseAction,
    handle_invoke_action,
    handle_retire_action,
    handle_revise_action,
)
from tl_core.integration.actor_access import holds_for, require_access
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
from tl_core.services.reserved import refuse_reserved, refuse_reserved_fields
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import effective_time
from tl_mod_documents.commands import API_COMMANDS as DOCUMENT_COMMANDS
from tl_mod_engineering.commands import API_COMMANDS

from tl_api.auth import AGENT_DIRECT_COMMANDS, current_principal, guard
from tl_api.context import get_ctx
from tl_api.effective import EFFECTIVE_AT_HEADER, resolve_effective_at

Handler = Callable[[UnitOfWork, Any], CommandResult]
Access = Literal[
    "admin", "controller", "company", "user"
]  # a typo is a type error, not an open door
SOURCE_PATTERN = r"^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]+)?$"
DEFAULT_SOURCE = "api"
CONTROLLER_PREFIX = "control.command."


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

    @property
    def name(self) -> str:
        return self.model.__name__


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
    CommandSpec(TransitionWorkflow, handle_transition_workflow),
    CommandSpec(PostToFeed, handle_post),
    CommandSpec(EditPost, handle_edit_post),
    CommandSpec(RetractPost, handle_retract_post),
    CommandSpec(ReactToPost, handle_react_to_post),
    CommandSpec(ChangeSetting, handle_change_setting),
    *(CommandSpec(c.model, c.handler, c.access) for c in API_COMMANDS),
    *(CommandSpec(c.model, c.handler, c.access) for c in DOCUMENT_COMMANDS),
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
)
"""Every command the API accepts. Void, mark-pins-stale and the file commands are not here:
voiding is not in the Phase 0 client contract, pin staleness is a system command, and files have
their own upload routes."""


COMMAND_BODIES: dict[str, type[BaseModel]] = {}
"""Every body model ``request_model`` made, by name: a test walks the routes against it."""


def request_model(model: type[Command], name: str) -> type[BaseModel]:
    """The body model for a command: its fields minus ``actor``, ``source`` made optional.

    Unknown fields (``actor`` included) are refused, and so is a reserved ``source``,
    ``correlation_id`` or ``causation_id`` (ADR-0014). Used for the commands here and for the
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
    upload routes included (ADR-0014; security re-review of b5f5d41).
    """
    if isinstance(data, dict):
        body = cast(dict[str, Any], data)
        refuse_reserved_fields(
            source=body.get("source"),
            correlation_id=body.get("correlation_id"),
            causation_id=body.get("causation_id"),
        )
    return data


def action_for(spec: CommandSpec) -> str:
    """The authorization action of a command: one explicit prefix per access level."""
    if spec.access == "admin":
        return f"admin.command.{spec.name}"
    if spec.access == "controller":
        return f"{CONTROLLER_PREFIX}{spec.name}"
    if spec.access in ("company", "user"):
        return f"command.{spec.name}"
    raise ValueError(f"unknown access {spec.access!r} for {spec.name}")  # fail closed at start-up


def controller_actions() -> frozenset[str]:
    """The exact ``control.command.<Name>`` actions a document controller may run (ADR-0013)."""
    return frozenset(action_for(spec) for spec in COMMANDS if spec.access == "controller")


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
        refuse_reserved(command)  # a client cannot pose as a publication (ADR-0014)
        if spec.access == "company" and command.scope == "company":
            ctx.authorizer.authorize(principal, f"admin.command.{spec.name}", request.url.path)
        when = resolve_effective_at(effective_at, command.scope)
        with effective_time(when), ctx.backend(False) as uow:
            if spec.needs_holds:
                from tl_api.routes.proposals import holds_access

                return cast(Any, spec.handler)(
                    uow, command, holds=lambda level: holds_access(principal, actor, level)
                )
            return spec.handler(uow, command)

    endpoint.__name__ = f"command_{spec.name}"
    endpoint.__doc__ = (spec.model.__doc__ or "").strip() or f"Run the {spec.name} command."
    endpoint.__annotations__["body"] = body_model
    return endpoint


def build_router() -> APIRouter:
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
        return "admin" if spec.access == "company" else spec.access

    def run(self, uow: UnitOfWork, command: Command) -> CommandResult:
        """Run ``command`` only if its own actor holds the access the table declares for it.

        The actor's access is resolved from the ledger in ``uow`` (``tl_core.integration.
        actor_access``), never from the caller, and the check fails closed: an unknown actor, a
        disabled account or a service actor with no live owner holds nothing. A handler that takes
        ``holds`` gets it from the same resolved access.
        """
        spec = self._specs[type(command).__name__]
        if command.actor.startswith("agent:") and spec.name not in AGENT_DIRECT_COMMANDS:
            # an agent proposes record changes (brief 18.12); the runner is not a way around it
            raise CommandAccessError(f"{spec.name}: an agent proposes, a person decides")
        needed: Access_ = "user"
        if spec.access in ("admin", "controller"):
            needed = spec.access
        elif spec.access == "company" and command.scope == "company":
            needed = "admin"
        held = require_access(uow.conn(), command.actor, needed, spec.name)
        if spec.needs_holds:
            return cast(Any, spec.handler)(uow, command, holds=holds_for(held))
        return spec.handler(uow, command)


def command_runner() -> TableCommandRunner:
    """The runner entry points pass to the rules worker, the inbound worker and the planner."""
    return TableCommandRunner()
