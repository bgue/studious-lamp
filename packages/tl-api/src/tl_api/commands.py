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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, create_model
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
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork

from tl_api.auth import AGENT_DIRECT_COMMANDS, guard
from tl_api.context import get_ctx

Handler = Callable[[UnitOfWork, Any], CommandResult]
SOURCE_PATTERN = r"^[a-z][a-z0-9_]*(:[A-Za-z0-9_.-]+)?$"
DEFAULT_SOURCE = "api"


@dataclass(frozen=True)
class CommandSpec:
    model: type[Command]
    handler: Handler

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
    CommandSpec(TransitionWorkflow, handle_transition_workflow),
    CommandSpec(PostToFeed, handle_post),
    CommandSpec(EditPost, handle_edit_post),
    CommandSpec(RetractPost, handle_retract_post),
    CommandSpec(ReactToPost, handle_react_to_post),
)
"""Every command the API accepts. Void, mark-pins-stale and the file commands are not here:
voiding is not in the Phase 0 client contract, pin staleness is a system command, and files have
their own upload routes."""


def request_model(model: type[Command], name: str) -> type[BaseModel]:
    """The body model for a command: its fields minus ``actor``, ``source`` made optional.

    Unknown fields (``actor`` included) are refused. Used for the commands here and for the
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
    return create_model(
        f"{name}Body",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def _make_endpoint(spec: CommandSpec, body_model: type[BaseModel]) -> Callable[..., CommandResult]:
    action = f"command.{spec.name}"
    changes_records = spec.name not in AGENT_DIRECT_COMMANDS

    def endpoint(
        request: Request,
        body: Any,
        actor: Annotated[str, Depends(guard(action, changes_records=changes_records))],
    ) -> CommandResult:
        ctx = get_ctx(request)
        fields = body.model_dump()
        if actor.startswith("agent:"):  # an agent cannot claim another source (brief 18.12)
            fields["source"] = source_for(actor)
        command = spec.model(**fields, actor=actor)
        with ctx.backend(False) as uow:
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
