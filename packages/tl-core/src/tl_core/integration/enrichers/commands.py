"""The enrichment commands a person uses: run one enricher on one record, accept or reject a value.

All three are ``user`` commands (FANOUT D12); the target type must allow ``SetPsetValues`` (the
accept path runs that allow-list and its guards, ADR-0010). None is an agent's direct tool: an
agent proposes. Accepting writes the enricher's own layer ``enrich.<name>`` only; promoting a value
to a real field is the person's own ``SetPsetValues``.

``RunEnricher`` runs the same pipeline as the dispatcher, as the enricher's service actor; the
caller only asks. It needs the enricher switched on, its app on, and the kill switch off.
"""

from __future__ import annotations

from pydantic import Field
from sqlalchemy import text

from tl_core.integration.enrichers.pipeline import (
    accept_value_by_person,
    in_scope,
    load_live_enricher,
    load_subject,
    reject_value_by_person,
    run_enricher,
)
from tl_core.integration.enrichers.registry import load_enricher, why_unusable
from tl_core.integration.errors import (
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.killswitch import kill_switch_on
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow


class RunEnricher(Command):
    """Run the enricher called ``enricher`` on one record now."""

    enricher: str
    record_id: str


class AcceptEnrichment(Command):
    """Accept a waiting value: it is written into the enricher's layer of the record."""

    value_id: str


class RejectEnrichment(Command):
    """Reject a waiting value. The same value is not proposed to a person again."""

    value_id: str
    reason: str = Field(min_length=1, max_length=1_000)


def handle_run_enricher(uow: UnitOfWork, cmd: RunEnricher) -> CommandResult:
    conn = uow.conn()
    if kill_switch_on(conn):
        raise IntegrationStateError("integrations are stopped (the kill switch is on)")
    enricher = load_live_enricher(conn, cmd.enricher)
    if enricher is None:
        raise IntegrationNotFoundError(f"no enricher {cmd.enricher} is switched on")
    subject = load_subject(conn, cmd.record_id)
    scope = conn.execute(
        text("SELECT scope FROM cur_core_record WHERE id = :i"), {"i": cmd.record_id}
    ).scalar()
    if subject is None or scope != cmd.scope or not in_scope(enricher, str(scope)):
        raise IntegrationNotFoundError(f"no record {cmd.record_id} in {cmd.scope} for it to read")
    plugin = load_enricher(enricher.name)
    unusable = why_unusable(plugin, enricher.name)
    if plugin is None or unusable is not None:
        raise InvalidIntegrationError(unusable or "the plugin cannot be loaded")
    stats, events = run_enricher(
        uow,
        enricher,
        plugin,
        subject,
        now=utcnow(),
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    del stats  # the events say what happened
    version = (events[-1].stream_version if events else subject.record.version) or 0
    return CommandResult(
        stream_id=cmd.record_id, key=subject.record.key, version=version, events=events
    )


def handle_accept_enrichment(uow: UnitOfWork, cmd: AcceptEnrichment) -> CommandResult:
    events = accept_value_by_person(
        uow,
        cmd.value_id,
        cmd.scope,
        by=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.value_id, key=None, version=events[-1].stream_version, events=events
    )


def handle_reject_enrichment(uow: UnitOfWork, cmd: RejectEnrichment) -> CommandResult:
    if not cmd.reason.strip():
        raise InvalidIntegrationError("a reason is required")
    events = reject_value_by_person(
        uow,
        cmd.value_id,
        cmd.scope,
        by=cmd.actor,
        reason=cmd.reason.strip(),
        source=cmd.source,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.value_id, key=None, version=events[-1].stream_version, events=events
    )


__all__ = [
    "AcceptEnrichment",
    "RejectEnrichment",
    "RunEnricher",
    "handle_accept_enrichment",
    "handle_reject_enrichment",
    "handle_run_enricher",
]
