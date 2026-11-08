"""The checks of dev/accept/P2-I2/S3.py: sign-off, issue and hold of an IWP."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from awp_world import SCOPE, World, refuses  # noqa: I001
from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.links.expected import (
    default_expected_links,
    missing_expected_links,
)
from tl_core.settings.service import set_setting
from tl_mod_awp import actions, errors
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.handlers.signoff import iwp_record_hash
from tl_schema.ddl_loader import statements

MINE = {
    c.model.__name__: c
    for c in AWP_COMMANDS
    if c.access.startswith(("awp.iwp.s", "awp.iwp.i", "awp.iwp.h"))
}
ROLES = "awp.release.signoff_roles"


def permit_registry():
    """The default expectations: ``schema/fixtures/links/awp.yaml`` carries the IWP's permit to
    work (``requires`` at Issued), so nothing is merged in here."""
    return default_expected_links()


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def build(db: Path) -> World:
    w = World(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.person("sam", ("user",), grant="superuser")
    w.editions()
    return w


def readiness(w: World, iwp: str, ready: bool, unknown: bool = False) -> None:
    """Write the readiness rows by hand (the readiness projection is S4's, not merged yet)."""
    with open_uow(w.db) as uow:
        conn = uow.conn()
        for table in ("cur_awp_readiness", "cur_awp_readiness_check"):
            if not conn.dialect.has_table(conn, table):
                for stmt in statements(
                    table, "sqlite" if conn.dialect.name == "sqlite" else "postgres"
                ):
                    conn.execute(text(stmt))
        for table in ("cur_awp_readiness_check", "cur_awp_readiness"):
            conn.execute(text(f"DELETE FROM {table} WHERE iwp_id = :i"), {"i": iwp})
        conn.execute(
            text(
                "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, "
                "facts_hash, as_of_seq) VALUES (:i, :s, '2026-11-07T08:00:00Z', '2026-11-07', "
                ":r, :h, 1)"
            ),
            {"i": iwp, "s": SCOPE, "r": ready, "h": "0" * 64},
        )
        if unknown:
            conn.execute(
                text(
                    "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, version, "
                    "state, as_of_seq) VALUES (:r, :s, :i, 'permit', '1', 'unknown', 1)"
                ),
                {"r": f"{iwp}:permit", "s": SCOPE, "i": iwp},
            )


def hash_of(w: World, iwp: str) -> str:
    with open_uow(w.db, readonly=True) as uow:
        return iwp_record_hash(uow.conn(), iwp)


def checks(w: World) -> None:
    said: list[str] = []

    def refused(error: type[BaseException], call) -> None:
        said.append(str(refuses(error, call)))

    iwp = partial(w.iwp, title="Rack secret", planned_start="2026-12-01", foreman="user:uma")
    a, b, c = iwp(), iwp(), iwp()
    w.call("uma", "AddIwpScope", iwp=a, items=w.items(["10.0", "20.0"]))

    def sign(who, i=a, rh=None):
        return w.call(who, "SignOffIwp", iwp=i, record_hash=rh or hash_of(w, i))

    def issue(who="sue", i=a, rh=None, **more):
        return w.call(who, "IssueIwp", iwp=i, record_hash=rh or hash_of(w, i), **more)

    with open_uow(w.db, readonly=True) as uow:
        for m in MINE.values():
            cmd = m.model.model_construct(actor="user:uma", source="test", scope=SCOPE)
            refuses(ForbiddenError, partial(require_command_access, uow.conn(), cmd))
    ok("user refused every command")
    refused(errors.IwpStateError, partial(sign, "sue"))
    ok("sign-off on a not-Ready IWP refused")
    for i in (a, c):
        w.set_status(i, "Ready")
    refused(errors.IwpNotReadyError, partial(sign, "sue"))
    readiness(w, a, False)
    refused(errors.IwpNotReadyError, partial(sign, "sue"))
    readiness(w, a, True, unknown=True)
    refused(errors.IwpNotReadyError, partial(sign, "sue"))
    readiness(w, a, True)
    ok("no row, ready false and an unknown check refused")
    refused(errors.IwpSignoffError, partial(sign, "sue", rh="0" * 64))
    ok("wrong hash refused")
    with open_uow(w.db) as uow:
        set_setting(
            uow,
            key=ROLES,
            layer=f"project:{SCOPE[8:]}",
            value=["user"],
            actor="user:ada",
            source="test",
            reason="t",
            accept_risk=True,
        )
    refused(errors.IwpSignoffError, partial(sign, "sue"))
    ok("a controller without the role refused")
    with open_uow(w.db) as uow:
        set_setting(
            uow,
            key=ROLES,
            layer=f"project:{SCOPE[8:]}",
            value=["superuser"],
            actor="user:ada",
            source="test",
            reason="t",
            accept_risk=True,
        )
    sign("sue")
    refused(errors.IwpSignoffError, partial(sign, "sue"))
    refused(errors.IwpSignoffError, partial(issue))
    sign("sam")
    ok("first ok, same signer twice refused, one signer cannot issue, second ok")
    rows = w.rows("SELECT signoffs_json FROM cur_awp_iwp WHERE id = :i", i=a)
    ok("projector holds the rows", rows[0]["signoffs_json"].count('"by"') == 2)
    made = issue(foreman="user:sam")
    with open_uow(w.db, readonly=True) as uow:
        gaps = missing_expected_links(uow, a, registry=permit_registry(), by_state="Issued")
    ok(
        "issued to the foreman",
        w.state(a) == "Issued" and w.column("cur_awp_iwp", "foreman", a) == "user:sam",
    )
    ok(
        "permit to work reported missing, not blocking",
        [g.expectation.display for g in gaps] == ["permit to work"] and len(made.events) == 2,
    )
    for i in (c,):
        readiness(w, i, True)
        sign("sue", i)
        sign("sam", i)
    w.set_status(c, "Constraint check")
    w.call("uma", "AddIwpScope", iwp=c, items=w.items(["5.0"]))
    w.set_status(c, "Ready")
    refused(errors.IwpSignoffError, partial(issue, i=c))
    ok("old signatures do not count after a change", True)
    w.call("sue", "HoldIwp", iwp=c, reason="Waiting")
    ok("hold from Ready", w.state(c) == "On hold")
    w.call("sue", "ReleaseHold", iwp=c)
    ok("release returns to Constraint check", w.state(c) == "Constraint check")
    w.call("sue", "HoldIwp", iwp=a, reason="Wait")
    w.call("sue", "ReleaseHold", iwp=a, reason="ok")
    w.set_status(a, "In progress")
    w.call("sue", "HoldIwp", iwp=a, reason="Wait")
    ok("hold from Issued and In progress", w.state(a) == "On hold")
    refused(errors.IwpStateError, partial(w.call, "sue", "HoldIwp", iwp=b, reason="x"))
    ok(
        "no refusal text holds a cell or a role list",
        not any("secret" in s or "superuser" in s for s in said),
    )
    ok(
        "RULES word equals command word",
        all(r.word == MINE[r.command].access for r in actions.RULES if r.command in MINE),
    )
    tables = ("cur_awp_iwp", "cur_core_record", "cur_links")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    ok(
        "rebuild equals incremental",
        before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables],
    )
