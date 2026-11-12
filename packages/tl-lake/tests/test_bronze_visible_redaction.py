"""A visible bronze row names no record the lake's reader may not read (P2-FIX-CONF F2).

The lake is read at the lowest clearance: an intent that names a restricted record reads "not
available" and a constraint payload with a restricted target reads as one with no target, on rows
that are themselves visible.
"""

from __future__ import annotations

import json
from typing import Any

from builder import SCOPE, LedgerBuilder
from tl_adapters.db import make_ledger, open_uow
from tl_core import confidentiality as cf
from tl_core.intent import NOT_AVAILABLE, Intent, IntentRef
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_lake import LakeConfig, read_snapshot, sync_lake
from tl_lake.duck import open_lake
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.testing import frozen_today


class _Cmd(Command):
    """A command carrier for seeding."""


def restricted(ledger: LedgerBuilder) -> str:
    cmd = _Cmd(actor="user:seed", source="test", scope=SCOPE)
    with frozen_today("2026-10-19"), cf.system_view(), open_uow(ledger.db) as uow:
        return create_item(
            uow,
            cmd,
            subject="RESTRICTEDSUBJECT",
            direction="in",
            medium="letter",
            received_via="manual",
            confidentiality="restricted",
            received_on="2026-10-19",
            received=True,
        ).stream_id


def put(
    ledger: LedgerBuilder, stream_type: str, event_type: str, payload: dict[str, Any], **kw: Any
) -> None:
    engine = ledger.engine()
    try:
        make_ledger(engine).append(
            stream_id="s-" + event_type,
            stream_type=stream_type,
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type=event_type, payload=payload, **kw)],
            actor="user:u",
            source="test",
            correlation_id="c-" + event_type,
        )
    finally:
        engine.dispose()


def test_a_visible_row_hides_what_the_lowest_viewer_may_not_read(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    secret = restricted(ledger)
    intent = Intent(next=[IntentRef(command="UpdateRecord", target=secret)])
    put(ledger, "test.Thing", "Thing.Created", {"k": "v"}, intent=intent)
    put(
        ledger,
        "core.Constraint",
        "Constraint.Raised",
        {"subject_id": "x", "target_kind": "record", "target_id": secret, "target_ref_type": None},
    )
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()
    with open_lake(lake, write=False) as con:
        rows = con.execute(
            "SELECT event_type, payload, intent FROM events"
            " WHERE event_type IN ('Thing.Created', 'Constraint.Raised')"
        ).fetchall()
    by_type = {r[0]: r for r in rows}
    assert secret not in str(rows)
    assert NOT_AVAILABLE in by_type["Thing.Created"][2]
    raised = json.loads(by_type["Constraint.Raised"][1])
    assert raised["target_id"] is None and raised["target_kind"] is None
    assert raised["subject_id"] == "x"
