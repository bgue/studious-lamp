"""The integration layer over HTTP: the calls that return a secret once, the dry runs and the reads.

Everything else an admin does to the layer is a command (``POST /commands/<Name>``). Three kinds of
call are not, and live here:

* **Create or rotate a secret** (``DefineAction``, ``RotateActionSecret``,
  ``CreateInboundEndpoint``, ``RotateInboundSecret``): the answer carries the new secret once.
  The text is in no event or projection, not logged, and not returned again; a lost secret is
  rotated.
* **Dry runs** (``DryRunRule`` over history, ``DryRunInboundMapping`` over a sample or a stored
  delivery): they write nothing.
* **Reads**: the registry (apps, actions, rules, endpoints, enrichers, values waiting for review,
  invocations) for any signed-in person; the inbound deliveries (the error queue) for an admin. No
  read returns a secret, a payload or an object key.

Writes and dry runs need the admin role (the guard actions are ``admin.integration.*``); an agent
has none of these routes (FANOUT D12).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from tl_core.integration.actions.service import (
    DefineAction,
    RotateActionSecret,
    define_action,
    rotate_action_secret,
)
from tl_core.integration.automation import first_error
from tl_core.integration.contract import (
    RULE_DRY_RUN_MAX_EVENTS,
    RULE_DRY_RUN_MAX_FIRINGS,
    Rule,
)
from tl_core.integration.errors import IntegrationNotFoundError, InvalidIntegrationError
from tl_core.integration.inbound.delivery import MappingDryRun, dry_run_mapping
from tl_core.integration.inbound.service import (
    CreateInboundEndpoint,
    RotateInboundSecret,
    create_endpoint,
    rotate_endpoint_secret,
)
from tl_core.integration.rules.dryrun import DryRun, draft_rule, dry_run_rule
from tl_core.integration.rules.engine import load_rule
from tl_core.integration.rules.service import rule_problems
from tl_core.webhooks.rows import load_json

from tl_api.auth import guard
from tl_api.commands import command_runner, request_model
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["integration"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Definer = Annotated[str, Depends(guard("admin.integration.action.define"))]
ActionRotator = Annotated[str, Depends(guard("admin.integration.action.rotate"))]
EndpointCreator = Annotated[str, Depends(guard("admin.integration.endpoint.create"))]
EndpointRotator = Annotated[str, Depends(guard("admin.integration.endpoint.rotate"))]
RuleDryRunner = Annotated[str, Depends(guard("admin.integration.rule.dry_run"))]
MappingDryRunner = Annotated[str, Depends(guard("admin.integration.endpoint.dry_run"))]
DeliveryReader = Annotated[str, Depends(guard("admin.integration.deliveries.read"))]
Reader = Annotated[str, Depends(guard("integration.read"))]
MAX_ROWS = 500

DefineActionBody = request_model(DefineAction, "DefineAction")
RotateActionSecretBody = request_model(RotateActionSecret, "RotateActionSecret")
CreateInboundEndpointBody = request_model(CreateInboundEndpoint, "CreateInboundEndpoint")
RotateInboundSecretBody = request_model(RotateInboundSecret, "RotateInboundSecret")


class SecretIssued(BaseModel):
    """A new secret, shown once. ``secret`` is the only place it ever appears."""

    id: str = Field(description="The definition id (action) or endpoint id.")
    secret_id: str | None
    version: int
    secret: str | None = Field(description="`whsec_...`; null for an action with no secret.")


@router.post(
    "/admin/integration/actions",
    operation_id="integration_define_action",
    response_model=SecretIssued,
)
def define(
    body: DefineActionBody,  # pyright: ignore[reportInvalidTypeForm]
    ctx: Ctx,
    actor: Definer,
) -> SecretIssued:
    """Define an action. A webhook action's signing secret is in the answer, once."""
    with ctx.backend(False) as uow:
        made = define_action(uow, DefineAction(**body.model_dump(), actor=actor))  # pyright: ignore[reportAttributeAccessIssue]
    return SecretIssued(
        id=made.definition_id,
        secret_id=made.secret_id,
        version=made.version,
        secret=None if made.secret is None else made.secret.secret,
    )


@router.post(
    "/admin/integration/actions/rotate-secret",
    operation_id="integration_rotate_action_secret",
    response_model=SecretIssued,
)
def rotate_action(
    body: RotateActionSecretBody,  # pyright: ignore[reportInvalidTypeForm]
    ctx: Ctx,
    actor: ActionRotator,
) -> SecretIssued:
    """Issue a new signing secret for a webhook action; the old one signs for the overlap."""
    with ctx.backend(False) as uow:
        made = rotate_action_secret(uow, RotateActionSecret(**body.model_dump(), actor=actor))  # pyright: ignore[reportAttributeAccessIssue]
    return SecretIssued(
        id=made.definition_id,
        secret_id=made.secret_id,
        version=made.version,
        secret=None if made.secret is None else made.secret.secret,
    )


@router.post(
    "/admin/integration/endpoints",
    operation_id="integration_create_endpoint",
    response_model=SecretIssued,
)
def create_inbound(
    body: CreateInboundEndpointBody,  # pyright: ignore[reportInvalidTypeForm]
    ctx: Ctx,
    actor: EndpointCreator,
) -> SecretIssued:
    """Create an inbound endpoint (disabled, in dry run); its signing secret is in the answer."""
    with ctx.backend(False) as uow:
        made = create_endpoint(uow, CreateInboundEndpoint(**body.model_dump(), actor=actor))  # pyright: ignore[reportAttributeAccessIssue]
    return SecretIssued(
        id=made.endpoint_id,
        secret_id=made.secret_id,
        version=made.version,
        secret=None if made.secret is None else made.secret.secret,
    )


@router.post(
    "/admin/integration/endpoints/rotate-secret",
    operation_id="integration_rotate_endpoint_secret",
    response_model=SecretIssued,
)
def rotate_inbound(
    body: RotateInboundSecretBody,  # pyright: ignore[reportInvalidTypeForm]
    ctx: Ctx,
    actor: EndpointRotator,
) -> SecretIssued:
    """Issue a new inbound secret; the old one verifies for the overlap (at most 24 hours)."""
    with ctx.backend(False) as uow:
        made = rotate_endpoint_secret(uow, RotateInboundSecret(**body.model_dump(), actor=actor))  # pyright: ignore[reportAttributeAccessIssue]
    return SecretIssued(
        id=made.endpoint_id,
        secret_id=made.secret_id,
        version=made.version,
        secret=None if made.secret is None else made.secret.secret,
    )


# --- dry runs -------------------------------------------------------------------------------------


class DryRunRuleBody(BaseModel):
    """Body of ``POST /admin/integration/rules/dry-run``: a stored rule or a draft, and a range."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    draft: dict[str, Any] | None = Field(
        default=None,
        description="A rule that is not stored: key, title, scope, when, condition, then, access.",
    )
    from_seq: int = Field(default=0, ge=0)
    to_seq: int | None = Field(default=None, ge=0)
    since: datetime | None = None
    until: datetime | None = None
    max_events: int = Field(default=RULE_DRY_RUN_MAX_EVENTS, ge=1, le=RULE_DRY_RUN_MAX_EVENTS)
    max_firings: int = Field(default=RULE_DRY_RUN_MAX_FIRINGS, ge=1, le=RULE_DRY_RUN_MAX_FIRINGS)


@router.post(
    "/admin/integration/rules/dry-run",
    operation_id="integration_dry_run_rule",
    response_model=DryRun,
)
def dry_run_a_rule(body: DryRunRuleBody, ctx: Ctx, actor: RuleDryRunner) -> DryRun:
    """What a rule would have done over past events. Nothing is written and nothing runs."""
    if (body.rule_id is None) == (body.draft is None):
        raise InvalidIntegrationError("give a rule id or a draft, not both")
    if body.rule_id is not None:
        with ctx.backend(True) as uow:
            stored = load_rule(uow.conn(), body.rule_id)
        if stored is None:
            raise IntegrationNotFoundError(f"no rule {body.rule_id}")
    else:
        assert body.draft is not None
        try:
            rule = Rule.model_validate(
                {
                    "mode": "propose",
                    "enabled": False,
                    "service_actor": f"svc:rule-{body.draft.get('key', 'draft')}",
                    "owner": actor,
                    **body.draft,
                }
            )
        except ValidationError as exc:
            raise InvalidIntegrationError(first_error(exc)) from exc
        problems = rule_problems(rule)
        if problems:
            raise InvalidIntegrationError("; ".join(p.message for p in problems)[:500])
        stored = draft_rule(rule)
    return dry_run_rule(
        ctx.backend,
        command_runner(),
        stored,
        from_seq=body.from_seq,
        to_seq=body.to_seq,
        since=body.since,
        until=body.until,
        max_events=body.max_events,
        max_firings=body.max_firings,
    )


class DryRunMappingBody(BaseModel):
    """Body of ``POST /admin/integration/endpoints/dry-run``."""

    model_config = ConfigDict(extra="forbid")

    scope: str
    endpoint_id: str
    sample: Any | None = Field(default=None, description="A payload to map.")
    delivery_id: str | None = Field(default=None, description="Or a stored delivery's payload.")


@router.post(
    "/admin/integration/endpoints/dry-run",
    operation_id="integration_dry_run_mapping",
    response_model=MappingDryRun,
)
def dry_run_a_mapping(body: DryRunMappingBody, ctx: Ctx, actor: MappingDryRunner) -> MappingDryRun:
    """The commands an endpoint's current mapping would run for a payload. Nothing is written."""
    with ctx.backend(True) as uow:
        return dry_run_mapping(
            uow,
            command_runner(),
            endpoint_id=body.endpoint_id,
            scope=body.scope,
            sample=body.sample,
            delivery_id=body.delivery_id,
        )


# --- reads ----------------------------------------------------------------------------------------

_TABLES: dict[str, tuple[str, str]] = {
    # kind: (table, order)
    "apps": ("cur_integration_app", "name"),
    "actions": ("cur_action_definition", "name"),
    "rules": ("cur_rule", "key"),
    "endpoints": ("cur_inbound_endpoint", "app, name"),
    "enrichers": ("cur_enricher", "name"),
    "invocations": ("cur_action_invocation", "seq DESC"),
    "enrichments": ("cur_enrichment_value", "seq DESC"),
}
_HIDDEN = frozenset({"executor_config_json"})


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    """A row with its ``*_json`` columns parsed (and named without the suffix)."""
    out: dict[str, Any] = {}
    for name, value in row.items():
        if name in _HIDDEN:
            continue
        if name.endswith("_json") and isinstance(value, (str, bytes)):
            out[name.removesuffix("_json")] = load_json(value)
        else:
            out[name] = value
    return out


class Rows(BaseModel):
    kind: str
    rows: list[dict[str, Any]]


@router.get("/integration/{kind}", operation_id="integration_list", response_model=Rows)
def list_registry(
    kind: str,
    ctx: Ctx,
    actor: Reader,
    state: Annotated[str | None, Query(max_length=40)] = None,
    target_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = 200,
) -> Rows:
    """One kind of integration record: ``apps``, ``actions``, ``rules``, ``endpoints``,
    ``enrichers``, ``invocations`` or ``enrichments`` (``state`` filters the values waiting for
    review). Never a secret, a payload or an executor's configuration."""
    if kind not in _TABLES:
        raise IntegrationNotFoundError(f"no integration kind {kind}")
    table, order = _TABLES[kind]
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if kind == "enrichments":
        if state is not None:
            clauses.append("acceptance_state = :state")
            params["state"] = state
        if target_id is not None:
            clauses.append("target_id = :target")
            params["target"] = target_id
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT :limit"  # noqa: S608
    with ctx.backend(True) as uow:
        found = uow.conn().execute(text(sql), params).mappings()
        rows = [_decode(dict(r)) for r in found]
    return Rows(kind=kind, rows=rows)


@router.get(
    "/admin/integration/deliveries", operation_id="integration_list_deliveries", response_model=Rows
)
def list_deliveries(
    ctx: Ctx,
    actor: DeliveryReader,
    state: Annotated[str | None, Query(max_length=20)] = None,
    endpoint_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = 200,
) -> Rows:
    """Inbound deliveries, newest first; ``state=failed`` is the error queue. No payload, no key."""
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if state is not None:
        clauses.append("state = :state")
        params["state"] = state
    if endpoint_id is not None:
        clauses.append("endpoint_id = :endpoint")
        params["endpoint"] = endpoint_id
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT delivery_id, endpoint_id, endpoint_version, scope, state, payload_sha256, "
        "payload_size, received_at, finished_at, attempts, error_code, error_message, "
        f"command_count FROM int_delivery{where} ORDER BY received_at DESC, delivery_id DESC "  # noqa: S608
        "LIMIT :limit"
    )
    with ctx.backend(True) as uow:
        rows = [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]
    return Rows(kind="deliveries", rows=rows)


__all__ = ["router"]
