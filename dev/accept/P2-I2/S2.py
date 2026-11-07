"""Acceptance for P2-I2-S2: IWP, scope item, constraint commands. ``--keep PATH`` seeds PATH."""

from __future__ import annotations

import argparse
import importlib.util as iu
import sys
import tempfile
from datetime import date
from functools import partial
from pathlib import Path

from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import actions, constraints, errors
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.facts import iwp_facts

AW = Path(__file__).parents[3] / "packages/tl-modules/awp/tests/awp_world.py"
spec = iu.spec_from_file_location("awp_world", AW)
aw = iu.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["awp_world"] = aw
spec.loader.exec_module(aw)  # type: ignore[union-attr]
MINE = {c.model.__name__: c for c in AWP_COMMANDS if "iwp" in c.access or "constr" in c.access}
H1, H2, ISO = "a" * 64, "b" * 64, ("ISO-1", "ISO-2")
EST = ("cur_awp_iwp", "estimated_hours")


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def build(db: Path):
    w = aw.World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    return w, w.documents(db.parent / "objects", *ISO)


def checks(w, docs: dict[str, str]) -> None:
    c = partial(w.call, "uma")
    rc = partial(c, "RaiseConstraint", constraint_type="Permit", owner="user:uma", description="x")
    mod = partial(w.module_call, constraints.raise_constraint, constraint_type="Permit")
    mod = partial(mod, owner="user:uma", description="y", need_by="2026-12-01")
    a, b, civ = (
        w.iwp(planned_start="2026-12-01", foreman="user:uma"),
        w.iwp(),
        w.iwp(discipline="CIV"),
    )
    keys = [w.column("cur_core_record", "key", i) for i in (a, b, civ)]
    ok("numbers", keys == ["P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"])
    with open_uow(w.db, readonly=True) as uow:
        for m in MINE.values():
            cmd = m.model.model_construct(actor="user:vera", source="test", scope=aw.SCOPE)
            aw.refuses(ForbiddenError, partial(require_command_access, uow.conn(), cmd))
    ok("viewer refused every command")
    s = w.items(["10.0", "20.0", "30.5"])
    c("AddIwpScope", iwp=a, items=s)
    with open_uow(w.db, readonly=True) as uow:
        ok("scope links", len(iwp_facts(uow.conn(), a).scope_ids["awp.ScopeItem"]) == 3)
    ok("hours derived", w.column(*EST, a) == "60.5")
    c("RemoveIwpScope", iwp=a, items=[s[2]])
    ok("hours recomputed", w.column(*EST, a) == "30.0")
    taken = aw.refuses(errors.ScopeTakenError, partial(c, "AddIwpScope", iwp=b, items=[s[0]]))
    ok("one iwp per item", "P123-IWP-PIP-0001" in str(taken))
    w.set_status(s[2], "Verified")
    aw.refuses(errors.ScopeRuleError, partial(c, "AddIwpScope", iwp=b, items=[s[2]]))
    w.set_status(s[2], None)
    ok("verified item refused")
    made = [
        c("CreateIwp", discipline="PIP", title="T", estimated_hours=h) for h in ("900.0", "5.0")
    ]
    got = [[x for e in r.events for x in e.payload.get("warnings", [])] for r in made]
    ok("sizing warnings", got == [["iwp_oversize"], ["iwp_undersize"]])
    w.set_status(b, "Ready")
    aw.refuses(errors.IwpStateError, partial(c, "AddIwpScope", iwp=b, items=s[:1]))
    w.set_status(b, None)
    ok("fields frozen at Ready")
    c("PinIwpDocument", iwp=a, document=docs[ISO[0]], pin="A")
    c("PinIwpDocument", iwp=a, document=docs[ISO[1]])
    pins = w.rows("SELECT pin FROM cur_links WHERE from_id = :i AND relation = 'references'", i=a)
    ok("pin with and without code", sorted(str(r["pin"]) for r in pins) == ["A", "None"])
    c("AddIwpScope", iwp=a, items=w.items(["400.0"] * 4))
    k = rc(iwp=a, source_kind="manual").stream_id
    ok("need_by default", w.column("cur_awp_constraint", "need_by", k) == "2026-11-03")
    c("SplitIwp", iwp=a, mode="by_hours", reason="big")
    new = w.rows("SELECT id FROM cur_awp_iwp WHERE foreman = 'user:uma' AND id <> :a", a=a)
    copied = [
        w.scalar("SELECT COUNT(*) FROM cur_links WHERE from_id = :i AND pin IS NOT NULL", i=n["id"])
        for n in new
    ]
    ok("split by_hours", len(new) == 2 and w.state(a) == "Split" and w.state(k) == "Void")
    ok("split copies pins and foreman", copied == [1, 1])
    y, x = w.iwp(), w.items(["1.0", "2.0", "3.0"])
    c("AddIwpScope", iwp=y, items=x)
    c("SplitIwp", iwp=y, mode="by_scope", groups=[x[:1], x[1:]], reason="hand")
    ok("split by_scope", w.state(y) == "Split")
    aw.refuses(errors.ConstraintRuleError, partial(rc, iwp=b, source_kind="manual"))
    ok("need_by refused without a date or start")
    for src in ("check", "rule", "feed_hold", "thread_hold"):
        aw.refuses(
            errors.ConstraintSourceError, partial(rc, iwp=b, source_kind=src, need_by="2026-12-01")
        )
        extra = dict(check_name="n", facts_hash=H1) if src == "check" else {}
        mod(iwp_id=b, source=src, **extra)
    ok("manual from user; four module sources refused and accepted through the function")
    done = dict(iwp_id=b, source="check", check_name="n2", facts_hash=H2)
    first = mod(**done)
    c("ClearConstraint", constraint=first.stream_id, reason="fine", resolved_by=s[0])
    links = w.rows(
        "SELECT from_id FROM cur_links WHERE relation = 'resolves' AND to_id = :i",
        i=first.stream_id,
    )
    ok("resolves link on clear", [r["from_id"] for r in links] == [s[0]])
    again, other = mod(**done), mod(**{**done, "facts_hash": H1})
    ok(
        "suppressed after a person's clear",
        (again.code, again.stream_id) == ("suppressed", first.stream_id),
    )
    ok(
        "a different hash raises a new one",
        other.stream_id != first.stream_id and other.code is None,
    )
    aw.refuses(
        RecordNotFoundError,
        partial(
            c,
            "ClearConstraint",
            constraint=other.stream_id,
            reason="x",
            resolved_by=aw.hidden_record(w),
        ),
    )
    ok("hidden resolved_by answers as missing")
    clear = partial(w.module_call, constraints.clear_constraint, constraint_id=other.stream_id)
    aw.refuses(errors.ConstraintSourceError, partial(clear, reason="x", by_source="rule"))
    ok("a check clears only what a check raised")
    row = {"raised_at": "2026-10-01T08:00:00Z", "cleared_at": None}
    aging = (
        constraints.is_aging(row, date(2026, 11, 7), 14),
        constraints.is_aging(row, date(2026, 10, 10), 14),
    )
    ok(
        "aging flag",
        constraints.constraint_age_days(row, date(2026, 11, 7)) == 37 and aging == (True, False),
    )
    ok(
        "RULES word equals command word",
        all(r.word == MINE[r.command].access for r in actions.RULES if r.command in MINE),
    )
    tables = (
        "cur_awp_iwp",
        "cur_awp_scope_item",
        "cur_awp_constraint",
        "cur_core_record",
        "cur_links",
    )
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    ok(
        "rebuild equals incremental",
        before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables],
    )


def seed(w, docs: dict[str, str]) -> None:
    """3 IWPs (Draft, In development, Constraint check), 40 scope items, 2 pins, 3 constraints."""
    c = partial(w.call, "uma")
    i1, i2, i3 = w.iwp(planned_start="2026-12-01"), w.iwp(), w.iwp()
    for target, hours in ((i1, ["1.0"] * 14), (i2, ["2.0"] * 13), (i3, ["3.0"] * 13)):
        c("AddIwpScope", iwp=target, items=w.items(hours))
    for n in ISO:
        c("PinIwpDocument", iwp=i1, document=docs[n], pin="A")
    c("StartIwpDevelopment", iwp=i2)
    c("StartIwpDevelopment", iwp=i3)
    c("SendIwpToConstraintCheck", iwp=i3)
    raised = [
        c(
            "RaiseConstraint",
            iwp=i1,
            constraint_type="Permit",
            source_kind="manual",
            owner="user:uma",
            description="Hold",
        ).stream_id
        for _ in range(3)
    ]
    c("AssignConstraint", constraint=raised[1], owner="user:sue")
    c("ClearConstraint", constraint=raised[2], reason="done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep")
    keep = parser.parse_args().keep
    checks(*build(Path(tempfile.mkdtemp()) / "s2.db"))
    if keep:
        Path(keep).parent.mkdir(parents=True, exist_ok=True)
        Path(keep).unlink(missing_ok=True)
        seed(*build(Path(keep)))
        print(f"PASS seed kept at {keep}")
    print("S2 ok")
