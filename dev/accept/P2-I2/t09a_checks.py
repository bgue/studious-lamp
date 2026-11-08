"""The checks of dev/accept/P2-I2/T09a.py: each prints ``PASS <name>`` or exits ``FAIL <name>``."""

from __future__ import annotations

import csv
import io
import re
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import s4_world as sw
import typer
from sqlalchemy import Connection
from tl_adapters.db import open_uow
from tl_cli.awp_report import ALL_NAMES, register
from tl_mod_awp import iwp_views
from tl_mod_awp.iwp_reports import (
    constraint_groups_report,
    constraint_log,
    iwp_readiness,
    iwp_status,
)
from tl_mod_awp.reports import to_csv
from typer.testing import CliRunner

SCOPE = sw.SCOPE
HEX64 = re.compile(r"[0-9a-f]{64}")


def ok(name: str, cond: Any = True) -> None:
    if not cond:
        sys.exit(f"FAIL {name}")
    print(f"PASS {name}")


def status_checks(conn: Connection, world: dict[str, Any]) -> None:
    body = iwp_status(conn, SCOPE)
    total, rows = body[-1], body[:-1]
    listed = iwp_views.iwp_list(conn, SCOPE, limit=500)
    hours = sum((i.estimated_hours or Decimal(0) for i in listed), Decimal(0))
    ok(
        "iwp_status: counts sum to the IWP count",
        len(listed) == 3 and sum(r.count for r in rows) == 3 and total.count == 3,
    )
    ok(
        "iwp_status: hours sum to the iwp_list hours, total row last",
        sum((r.estimated_hours for r in rows), Decimal(0)) == hours == Decimal("22.5")
        and total.state == "total"
        and total.estimated_hours == hours,
    )
    ok(
        "iwp_status: workflow order (Draft before Constraint check)",
        [r.state for r in rows] == ["Draft", "Constraint check"],
    )


def readiness_checks(conn: Connection, world: dict[str, Any]) -> None:
    w = world["w"]
    key = {k: w.column("cur_core_record", "key", world[k]) for k in ("a", "b", "c")}
    rows = {r.number: r for r in iwp_readiness(conn, SCOPE)}
    a, b, c = rows.get(key["a"]), rows.get(key["b"]), rows.get(key["c"])
    ok(
        "iwp_readiness: evaluated, blocked names listed, n_a not counted as blocked",
        a is not None
        and (a.ready, a.passing, a.total, a.blocked)
        == ("no", "1", "4", "constraints_cleared, zz_a, zz_b"),
    )
    ok(
        "iwp_readiness: evaluated ready",
        b is not None and (b.ready, b.passing, b.total, b.blocked) == ("yes", "2", "2", "-"),
    )
    ok(
        "iwp_readiness: never evaluated",
        c is not None
        and (c.ready, c.passing, c.total, c.blocked) == ("not evaluated", "-", "-", "-"),
    )


def leak_checks(conn: Connection, world: dict[str, Any]) -> None:
    rendered = [
        to_csv(iwp_status(conn, SCOPE)),
        to_csv(iwp_readiness(conn, SCOPE)),
        to_csv(constraint_log(conn, SCOPE)),
        *(to_csv(constraint_groups_report(conn, SCOPE, by)) for by in ("category", "owner", "age")),
    ]
    blob = "\n".join(rendered)
    ids = [r["id"] for r in world["w"].rows("SELECT id FROM cur_core_record")]
    ok("reports: no 64-hex string", not HEX64.search(blob))
    ok("reports: no record id", not any(i in blob for i in ids))
    ok(
        "reports: no resolve_via text, no hidden key",
        "resolve_via" not in blob and "CON-HID" not in blob,
    )


def constraint_checks(conn: Connection, world: dict[str, Any]) -> None:
    log = constraint_log(conn, SCOPE)
    # The expected keys are every constraint record but the hidden one: the blocked checks of
    # the evaluation raise check-sourced constraints too (ADR-0017), and they are visible.
    visible = world["w"].rows(
        "SELECT key FROM cur_core_record WHERE type = 'core.Constraint' AND id <> :h",
        h=world["hidden_con"],
    )
    ok(
        "constraint_log: hidden subject's constraint left out",
        sorted(r.key for r in log) == sorted(r["key"] for r in visible),
    )
    blocking = sum(1 for r in log if r.severity == "blocking")
    for by in ("category", "owner", "age"):
        groups = constraint_groups_report(conn, SCOPE, by)
        ok(
            f"{by}: groups agree with constraint_log on the total",
            sum(g.count for g in groups) == len(log)
            and sum(g.blocking for g in groups) == blocking,
        )


def csv_checks(conn: Connection) -> None:
    reports = {
        "iwp_status": iwp_status(conn, SCOPE),
        "iwp_readiness": iwp_readiness(conn, SCOPE),
        "constraint_log": constraint_log(conn, SCOPE),
        "constraints_by_category": constraint_groups_report(conn, SCOPE, "category"),
        "constraints_by_owner": constraint_groups_report(conn, SCOPE, "owner"),
        "constraints_by_age": constraint_groups_report(conn, SCOPE, "age"),
    }
    for name, rows in reports.items():
        parsed = list(csv.reader(io.StringIO(to_csv(rows))))
        ok(
            f"csv {name}: header, then rows+1 lines",
            parsed[0] == list(type(rows[0]).model_fields) and len(parsed) == len(rows) + 1,
        )


def cli_checks(world: dict[str, Any]) -> None:
    app = typer.Typer()
    register(app)
    copy = Path(shutil.copy(world["db"], world["db"].with_name("copy.db")))
    runner = CliRunner()
    good = runner.invoke(
        app,
        ["report", "constraints_by_owner", "--csv", "--project", "P123", "--db", str(copy)],
    )
    ok(
        "cli: constraints_by_owner --csv exits 0 with its header",
        good.exit_code == 0 and good.output.startswith("label,count,blocking,aging\n"),
    )
    bad = runner.invoke(app, ["report", "nope", "--project", "P123", "--db", str(copy)])
    ok(
        "cli: unknown name exits 1 and lists all nine names",
        bad.exit_code == 1
        and all(name in bad.output for name in ALL_NAMES)
        and len(ALL_NAMES) == 9,
    )
    ok("cli: no Traceback", "Traceback" not in good.output + bad.output)


def checks(world: dict[str, Any]) -> None:
    with open_uow(world["w"].db, readonly=True) as uow:
        conn = uow.conn()
        status_checks(conn, world)
        readiness_checks(conn, world)
        leak_checks(conn, world)
        constraint_checks(conn, world)
        csv_checks(conn)
    cli_checks(world)
