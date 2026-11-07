"""The seed and the hidden-record source of dev/accept/P2-I2/T04a.py (kept here so the script stays
short). Built on the awp test world (``awp_world``) and the core constraint commands, as C2 is.

Seed: IWP ``i1`` (Draft, PIP, foreman uma, linked to CWP ``cwp``, 40 scope items, 2 pins), ``i2``
(In development, PIP, 13 items) and ``i3`` (Constraint check, CIV, 13 items). Constraints: one open
(on i1), one Assigned (on i2), one cleared (on i3).
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from awp_world import SCOPE, World  # noqa: I001
from sqlalchemy import event, text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.constraints import command_table
from tl_core.modules import ConfidentialSource
from tl_mod_awp.names import CWP, IWP

ISO = ("ISO-1", "ISO-2")
CMDS = {c.model.__name__: c for c in command_table()}
RESTRICTED_VIEWER = cf.Viewer("user:ctl", 1, "user:ctl")
CLASS_TABLE = "t04a_class"


class Ledger(World):
    def run(self, who: str, name: str, **f: Any) -> Any:
        spec = CMDS[name]
        cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **f)
        with open_uow(self.db) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return spec.handler(uow, cmd)

    def raise_(self, subject: str, **f: Any) -> Any:
        base = dict(
            phase="ready",
            severity="blocking",
            category="materials",
            owner="user:uma",
            due_at="2026-12-01",
        )
        return self.run("uma", "RaiseConstraint", subject=subject, **{**base, **f})


def build(db: Path) -> tuple[Ledger, dict[str, Any]]:
    w = Ledger(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    w.areas_and_path(("A1",))
    docs = w.documents(db.parent / "objects", *ISO)
    cwp = w.new_cwp(
        "PIP",
        "Pipe spools",
        "A1",
        planned_start="2026-11-02",
        planned_finish="2027-01-29",
        budget_hours="100.0",
    )
    return w, {"docs": docs, "cwp": cwp}


def seed(w: Ledger, ctx: dict[str, Any]) -> dict[str, str]:
    """The IWP ids by name (``i1``, ``i2``, ``i3``) and the CWP id (``cwp``)."""
    c = partial(w.call, "uma")
    i1 = w.iwp(planned_start="2026-12-01", foreman="user:uma", cwp_id=ctx["cwp"])
    i2 = w.iwp()
    i3 = w.iwp(discipline="CIV")
    for target, hours in ((i1, ["1.0"] * 40), (i2, ["2.0"] * 13), (i3, ["3.0"] * 13)):
        c("AddIwpScope", iwp=target, items=w.items(hours))
    for n in ISO:
        c("PinIwpDocument", iwp=i1, document=ctx["docs"][n], pin="A")
    c("StartIwpDevelopment", iwp=i2)
    c("StartIwpDevelopment", iwp=i3)
    c("SendIwpToConstraintCheck", iwp=i3)
    open_one = w.raise_(i1, description="Spools late")
    assigned = w.raise_(i2, category="permit", description="Hot work permit")
    w.run("uma", "AssignConstraint", constraint=assigned.stream_id, owner="user:uma")
    cleared = w.raise_(i3, category="engineering", description="Drawing open")
    w.run(
        "uma",
        "ClearConstraint",
        constraint=cleared.stream_id,
        reason="Issued",
        cleared_at="2026-10-20",
    )
    return {"i1": i1, "i2": i2, "i3": i3, "cwp": ctx["cwp"], "open": str(open_one.stream_id)}


def classed(w: Ledger, hidden: set[str]) -> None:
    """Give every awp IWP and CWP a class (restricted for ``hidden``, internal otherwise) and make
    the class count, as ``test_five_readers`` does for awp records (a test-only source)."""
    with open_uow(w.db) as uow:
        conn = uow.conn()
        conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        everything = conn.execute(
            text("SELECT id FROM cur_core_record WHERE type IN (:a, :b)"),
            {"a": IWP, "b": CWP},
        ).all()
        for (record_id,) in everything:
            conn.execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {
                    "i": str(record_id),
                    "c": "restricted" if str(record_id) in hidden else "internal",
                },
            )
    source = ConfidentialSource(
        record_types=frozenset({IWP, CWP}), table=CLASS_TABLE, id_column="id", class_column="cls"
    )
    original = cf.confidential_sources
    cf.confidential_sources = lambda: [*original(), source]


def statements(w: Ledger, fn: Any) -> int:
    """How many SQL statements ``fn(conn)`` runs (a ``before_cursor_execute`` listener)."""
    seen: list[str] = []

    def hook(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        seen.append(statement)

    with open_uow(w.db, readonly=True) as uow:
        engine = uow.conn().engine
        event.listen(engine, "before_cursor_execute", hook)
        try:
            fn(uow.conn())
        finally:
            event.remove(engine, "before_cursor_execute", hook)
    return len(seen)
