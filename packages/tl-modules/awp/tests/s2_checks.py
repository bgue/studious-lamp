"""The checks and the seed of dev/accept/P2-I2/S2.py (kept here so the script stays short)."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from awp_world import SCOPE, World, refuses  # noqa: I001
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_mod_awp import actions, errors
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.facts import iwp_facts

MINE = {c.model.__name__: c for c in AWP_COMMANDS if "iwp" in c.access}
ISO = "a" * 64, "b" * 64, ("ISO-1", "ISO-2")
EST = ("cur_awp_iwp", "estimated_hours")


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def build(db: Path):
    w = World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    return w, w.documents(db.parent / "objects", *ISO)


def checks(w, docs: dict[str, str]) -> None:
    c = partial(w.call, "uma")
    a, b, civ = (
        w.iwp(planned_start="2026-12-01", foreman="user:uma"),
        w.iwp(),
        w.iwp(discipline="CIV"),
    )
    keys = [w.column("cur_core_record", "key", i) for i in (a, b, civ)]
    ok("numbers", keys == ["P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"])
    with open_uow(w.db, readonly=True) as uow:
        for m in MINE.values():
            cmd = m.model.model_construct(actor="user:vera", source="test", scope=SCOPE)
            refuses(ForbiddenError, partial(require_command_access, uow.conn(), cmd))
    ok("viewer refused every command")
    s = w.items(["10.0", "20.0", "30.5"])
    c("AddIwpScope", iwp=a, items=s)
    with open_uow(w.db, readonly=True) as uow:
        ok("scope links", len(iwp_facts(uow.conn(), a).scope_ids["awp.ScopeItem"]) == 3)
    ok("hours derived", w.column(*EST, a) == "60.5")
    c("RemoveIwpScope", iwp=a, items=[s[2]])
    ok("hours recomputed", w.column(*EST, a) == "30.0")
    taken = refuses(errors.ScopeTakenError, partial(c, "AddIwpScope", iwp=b, items=[s[0]]))
    ok("one iwp per item", "P123-IWP-PIP-0001" in str(taken))
    w.set_status(s[2], "Verified")
    refuses(errors.ScopeRuleError, partial(c, "AddIwpScope", iwp=b, items=[s[2]]))
    w.set_status(s[2], None)
    ok("verified item refused")
    made = [
        c("CreateIwp", discipline="PIP", title="T", estimated_hours=h) for h in ("900.0", "5.0")
    ]
    got = [
        [g["message"] for e in r.events for g in e.payload.get("guards_evaluated", [])]
        for r in made
    ]
    ok("sizing warnings", got == [["iwp_oversize"], ["iwp_undersize"]])
    w.set_status(b, "Ready")
    refuses(errors.IwpStateError, partial(c, "AddIwpScope", iwp=b, items=s[:1]))
    w.set_status(b, None)
    ok("fields frozen at Ready")
    c("PinIwpDocument", iwp=a, document=docs[ISO[0]], pin="A")
    c("PinIwpDocument", iwp=a, document=docs[ISO[1]])
    pins = w.rows("SELECT pin FROM cur_links WHERE from_id = :i AND relation = 'references'", i=a)
    ok("pin with and without code", sorted(str(r["pin"]) for r in pins) == ["A", "None"])
    c("AddIwpScope", iwp=a, items=w.items(["400.0"] * 4))
    c("SplitIwp", iwp=a, mode="by_hours", reason="big")
    new = w.rows("SELECT id FROM cur_awp_iwp WHERE foreman = 'user:uma' AND id <> :a", a=a)
    copied = [
        w.scalar("SELECT COUNT(*) FROM cur_links WHERE from_id = :i AND pin IS NOT NULL", i=n["id"])
        for n in new
    ]
    ok("split by_hours", len(new) == 2 and w.state(a) == "Split")
    ok("split copies pins and foreman", copied == [1, 1])
    y, x = w.iwp(), w.items(["1.0", "2.0", "3.0"])
    c("AddIwpScope", iwp=y, items=x)
    c("SplitIwp", iwp=y, mode="by_scope", groups=[x[:1], x[1:]], reason="hand")
    ok("split by_scope", w.state(y) == "Split")
    ok(
        "RULES word equals command word",
        all(r.word == MINE[r.command].access for r in actions.RULES if r.command in MINE),
    )
    tables = (
        "cur_awp_iwp",
        "cur_awp_scope_item",
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
    """3 IWPs (Draft, In development, Constraint check), 40 scope items, 2 pins."""
    c = partial(w.call, "uma")
    i1, i2, i3 = w.iwp(planned_start="2026-12-01"), w.iwp(), w.iwp()
    for target, hours in ((i1, ["1.0"] * 14), (i2, ["2.0"] * 13), (i3, ["3.0"] * 13)):
        c("AddIwpScope", iwp=target, items=w.items(hours))
    for n in ISO:
        c("PinIwpDocument", iwp=i1, document=docs[n], pin="A")
    c("StartIwpDevelopment", iwp=i2)
    c("StartIwpDevelopment", iwp=i3)
    c("SendIwpToConstraintCheck", iwp=i3)
