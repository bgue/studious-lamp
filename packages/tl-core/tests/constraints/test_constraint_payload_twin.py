"""A constraint event never names a record the viewer may not read (P2-FIX-CONF, ADR-0024 F7).

The ``Constraint.Raised`` payload carries the target and ``Constraint.Cleared`` the record that
resolved it. For a viewer who cannot read that record the event reads byte for byte as one of a
constraint raised (or cleared) with no such reference. Runs on every adapter the root conftest
offers (Postgres under ``--adapters sqlite,postgres``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-INS"
sys.path.insert(0, str(ACCEPT))
import s1_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.constraints import clear_constraint  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402
from tl_core.intent import redact_for_viewer  # noqa: E402
from tl_core.services.queries import record_history  # noqa: E402

CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")


def _events(built: sw.World, constraint: str, viewer: cf.Viewer, kind: str) -> str:
    with open_uow(built.w.db, readonly=True) as uow, cf.use_viewer(viewer):
        found = [e for e in record_history(uow, constraint) if e.event_type == kind]
    assert len(found) == 1
    payload = {k: v for k, v in found[0].payload.items() if k != "constraint_id"}
    return json.dumps(payload, sort_keys=True)


def _raise(built: sw.World, **target: str) -> str:
    with cf.system_view():
        return str(built.w.modraise(built.iwp, "rule", **target).constraint_id)


def test_a_hidden_target_reads_as_no_target(db: str | Path, tmp_path: Path) -> None:
    built = sw.build(tmp_path, db)
    hidden = sw.add_hidden(built)
    named = _raise(built, target_id=hidden)
    bare = _raise(built)
    seen = _events(built, named, cf.LOWEST, "Constraint.Raised")
    assert hidden not in seen
    assert seen == _events(built, bare, cf.LOWEST, "Constraint.Raised")  # byte for byte
    assert hidden in _events(built, named, CONTROLLER, "Constraint.Raised")


def test_a_visible_target_is_kept(db: str | Path, tmp_path: Path) -> None:
    built = sw.build(tmp_path, db)
    named = _raise(built, target_id=built.ids["to"])
    assert built.ids["to"] in _events(built, named, cf.LOWEST, "Constraint.Raised")


def test_a_hidden_resolver_reads_as_no_resolver(db: str | Path, tmp_path: Path) -> None:
    built = sw.build(tmp_path, db)
    hidden = sw.add_hidden(built)
    named, bare = _raise(built), _raise(built)
    with cf.system_view():
        for cid, by in ((named, hidden), (bare, None)):
            built.w.mod(
                clear_constraint, constraint_id=cid, reason="r", by_module="awp", resolved_by=by
            )
    seen = _events(built, named, cf.LOWEST, "Constraint.Cleared")
    assert hidden not in seen
    cleared = json.loads(seen)
    other = json.loads(_events(built, bare, cf.LOWEST, "Constraint.Cleared"))
    cleared.pop("cleared_at")
    other.pop("cleared_at")
    assert cleared == other


def test_the_activity_feed_and_the_event_read_redact_too(db: str | Path, tmp_path: Path) -> None:
    built = sw.build(tmp_path, db)
    hidden = sw.add_hidden(built)
    named = _raise(built, target_id=hidden)
    with open_uow(built.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
        page = record_activity(uow, named, revisions_only=False)
        read = redact_for_viewer(
            uow.conn(), cf.filter_events(uow.conn(), uow.ledger.read_after(0, limit=100_000))
        )
    assert hidden not in "".join(r.event.model_dump_json() for r in page.rows)
    assert hidden not in "".join(e.model_dump_json() for e in read if e.stream_type != "core.Link")
