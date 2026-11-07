"""Helpers of dev/accept/P2-I2/S4.py: stand-in checks, a fake clock, events and a world."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
import tl_adapters.sqlite.uow as sqlite_uow  # noqa: E402
from awp_world import SCOPE, World  # noqa: E402,I001
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow  # noqa: E402
from tl_core import constraints  # noqa: E402
from tl_core.ledger import Event  # noqa: E402
from tl_core.projection.defaults import default_registry  # noqa: E402
from tl_core.readiness.types import CheckResult, RecordRef  # noqa: E402
from tl_core.util import new_ulid, utcnow  # noqa: E402
from tl_mod_awp.readiness.checks import ConstraintsCleared  # noqa: E402
from tl_mod_awp.readiness.projector import readiness_projectors  # noqa: E402
from tl_schema.ddl_loader import statements  # noqa: E402

TODAY = date(2026, 11, 7)
SOURCE_EVENTS = "SELECT payload FROM events WHERE stream_id = :i AND event_type = :t ORDER BY seq"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Stand:
    """A test stand-in check; ``mode`` is answer, raise, slow, many (33 results) or over."""

    version = "1"

    def __init__(self, name: str, state: str = "ok", mode: str = "answer", watches=("awp.IWP",)):
        self.name, self.state, self.mode = name, state, mode
        self.watches = frozenset(watches)
        self.refs: list[RecordRef] = []
        self.clock: Clock | None = None

    def evaluate(self, conn: Any, iwp: Any, today: date) -> Any:
        one = CheckResult(
            name=self.name,
            version="1",
            state=self.state,
            detail="fixed words",
            resolve_via=self.refs,
        )
        if self.mode == "raise":
            raise RuntimeError("boom /secret/path")
        if self.mode == "slow" and self.clock is not None:
            self.clock.now += 11
        if self.mode == "many":
            return [one] * 33
        if self.mode == "over":
            return CheckResult.model_construct(
                **{
                    **one.model_dump(),
                    "resolve_via": [RecordRef(record_id="x", record_type="t", key="k")] * 51,
                }
            )
        return one


def checks(*stands: Stand) -> dict[str, Any]:
    return {c.name: c for c in (ConstraintsCleared(), *stands)}


def build(db: Path) -> World:
    sqlite_uow.default_registry = lambda: registry()  # type: ignore[assignment]
    w = World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    return w


def registry() -> Any:
    reg = default_registry()
    for projector in readiness_projectors():
        reg.register(projector)
    return reg


def c2_ready() -> bool:
    try:
        constraints.open_blocking(None, "x", "ready")  # type: ignore[arg-type]
    except NotImplementedError:
        return False
    except Exception:  # noqa: BLE001 - any other error means the body exists
        return True
    return True


def payloads(w: World, iwp: str, event_type: str) -> list[str]:
    return [r["payload"] for r in w.rows(SOURCE_EVENTS, i=iwp, t=event_type)]


def count(w: World, iwp: str, event_type: str) -> int:
    return len(payloads(w, iwp, event_type))


def run(w: World, fn: Any, *args: Any, **kwargs: Any) -> Any:
    with open_uow(w.db) as uow:
        return fn(uow, *args, **kwargs)


def fake_event(stream_type: str, stream_id: str, source: str = "test") -> Event:
    now = utcnow()
    return Event(
        event_type="X.Changed",
        payload={},
        seq=1,
        event_id=new_ulid(),
        stream_id=stream_id,
        stream_type=stream_type,
        stream_version=1,
        scope=SCOPE,
        actor="user:uma",
        recorded_at=now,
        effective_at=now,
        correlation_id=new_ulid(),
        causation_id=None,
        source=source,
        prev_hash=None,
        hash="0" * 64,
    )


def tables(w: World) -> list[Any]:
    head = w.rows("SELECT * FROM cur_awp_readiness ORDER BY iwp_id")
    rows = w.rows("SELECT * FROM cur_awp_readiness_check ORDER BY row_id")
    return [head, rows]


def fake_c2(w: World) -> list[dict[str, Any]]:
    """Stand-ins for the C2 bodies while they raise NotImplementedError; the raises recorded.
    The constraint table (a C2 projector) is made by hand from its generated DDL."""
    with open_uow(w.db) as uow:
        for stmt in statements("cur_core_constraint", "sqlite"):
            uow.conn().execute(text(stmt))
    seen: list[dict[str, Any]] = []

    def raised(uow: Any, **kw: Any) -> constraints.ConstraintOutcome:
        seen.append(kw)
        return constraints.ConstraintOutcome(constraint_id=new_ulid(), key=None, action="raised")

    constraints.raise_constraint = raised  # type: ignore[assignment]
    return seen


def constraint_row(w: World, iwp: str, phase: str, severity: str, status: str | None) -> str:
    """A constraint row written by hand (projection rows; the check only reads them)."""
    cid, now = new_ulid(), "2026-11-07T08:00:00Z"
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_core_record (id, type, scope, title, status, version, last_seq, "
                "created_at, updated_at) VALUES (:i, 'core.Constraint', :s, 'c', :st, 1, 1, :n, :n)"
            ),
            {"i": cid, "s": SCOPE, "st": status, "n": now},
        )
        uow.conn().execute(
            text(
                "INSERT INTO cur_core_constraint (id, scope, subject_id, phase, severity, "
                "category, "
                "source, last_seq) VALUES (:i, :s, :w, :p, :v, 'other', 'manual', 1)"
            ),
            {"i": cid, "s": SCOPE, "w": iwp, "p": phase, "v": severity},
        )
    return cid
