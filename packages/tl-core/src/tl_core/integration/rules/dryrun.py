"""Dry run of a rule against history (brief §18.8; FANOUT D7).

A stored rule or a draft is run over a range of past events (a seq range or a time range, at most
``RULE_DRY_RUN_MAX_EVENTS`` read and ``RULE_DRY_RUN_MAX_FIRINGS`` reported). Nothing is written and
no command runs: each command is built, validated and access-checked and reported as a
``PlannedCommand``. The *when* is exact on history. The *if* is evaluated on the record **as it is
now** (``condition_basis = "current"``): as-of evaluation waits for the time-travel reads of P1-I6.
The kill switch and the moment the rule was switched on are ignored: a dry run asks what the rule
would have done.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import text

from tl_core.confidentiality import use_viewer
from tl_core.integration.contract import (
    RULE_DRY_RUN_MAX_EVENTS,
    RULE_DRY_RUN_MAX_FIRINGS,
    CommandRunner,
    Rule,
    RuleFiring,
)
from tl_core.integration.rules.engine import StoredRule, plan_firing
from tl_core.integration.visibility import declared_viewer, event_hidden
from tl_core.webhooks.base import UowFactory, iso_z
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import OUTBOX_COLUMNS, OutboxRow


class DryRun(BaseModel):
    """What a rule would have done over a range of events."""

    rule: str
    rule_version: int
    events_read: int
    #: True when the range held more events or firings than the limits allow.
    truncated: bool = False
    firings: list[RuleFiring] = Field(default_factory=list[RuleFiring])


def draft_rule(rule: Rule, *, rule_id: str = "draft") -> StoredRule:
    """A rule that is not stored yet, as the planner reads it."""
    return StoredRule(
        rule_id=rule_id,
        key=rule.key,
        title=rule.title,
        scope=rule.scope,
        version=rule.version,
        when=WebhookFilter.from_dict(rule.when),
        condition=rule.condition,
        steps=tuple(rule.then),
        mode=rule.mode,
        service_actor=rule.service_actor,
        access=rule.access,
        enabled=True,
        enabled_from_seq=0,
        integration_app=None,
    )


def dry_run_rule(
    open_uow: UowFactory,
    runner: CommandRunner,
    rule: StoredRule,
    *,
    from_seq: int = 0,
    to_seq: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    max_events: int = RULE_DRY_RUN_MAX_EVENTS,
    max_firings: int = RULE_DRY_RUN_MAX_FIRINGS,
) -> DryRun:
    """Plan ``rule`` over the events in range. A seq range and a time range both narrow."""
    clauses = ["seq > :after"]
    params: dict[str, object] = {"after": max(0, from_seq - 1)}
    if to_seq is not None:
        clauses.append("seq <= :to_seq")
        params["to_seq"] = to_seq
    if since is not None:
        clauses.append("recorded_at >= :since")
        params["since"] = iso_z(since)
    if until is not None:
        clauses.append("recorded_at <= :until")
        params["until"] = iso_z(until)
    sql = (
        f"SELECT {OUTBOX_COLUMNS} FROM outbox_events WHERE {' AND '.join(clauses)} "
        "ORDER BY seq LIMIT :limit"
    )
    ignoring_the_switch = replace(rule, enabled_from_seq=0)
    report = DryRun(rule=rule.key, rule_version=rule.version, events_read=0)
    with open_uow(readonly=True) as uow:
        found = uow.conn().execute(text(sql), {**params, "limit": max_events + 1}).mappings()
        rows = [OutboxRow.from_mapping(row) for row in found]
        if len(rows) > max_events:
            rows = rows[:max_events]
            report.truncated = True
        report.events_read = len(rows)
        # read as the rule would: an event about a record its actor may not read is not in a dry
        # run either (ADR-0016)
        viewer = declared_viewer(rule.service_actor, rule.access)
        for row in rows:
            if event_hidden(uow.conn(), row, viewer):
                continue
            with use_viewer(viewer):
                plan = plan_firing(uow, runner, ignoring_the_switch, row)
            if plan is None:
                continue
            if len(report.firings) >= max_firings:
                report.truncated = True
                break
            report.firings.append(
                RuleFiring(
                    rule=rule.key,
                    rule_version=rule.version,
                    event_id=row.event_id,
                    seq=row.seq,
                    depth=plan.depth,
                    outcome=plan.outcome,
                    condition_basis="current",
                    planned=plan.planned,
                    problems=plan.problems,
                )
            )
    return report
