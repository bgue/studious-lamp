"""Acceptance for P2-I1-T01: the awp loaders awp-wbs and awp-cwa and their sample files (SQLite).

Run: ``uv run python dev/accept/P2-I1/T01.py``. The ``tl load`` commands run in a scratch ledger.
"""

from __future__ import annotations

import re
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_mod_cost.testing import CostWorld, row
from typer.testing import CliRunner

PW = "correct horse battery"
PROJECT = "P123"
SAMPLES = Path(str(files("tl_mod_awp") / "samples"))
OPENED = re.compile(r"opened (\S+)")
PLANNED = re.compile(r"planned \S+ new (\d+) existing (\d+) invalid (\d+)")


def ok(good: bool, what: str) -> None:
    assert good, what
    print("PASS", what)


def main(work: Path) -> None:
    db = as_target(str(work / "t.db"))
    create_schema(db)
    CostWorld(db).import_snapshot([row(c, c) for c in ("WLD", "ERC", "TST")])
    word = prepare_password(PW, username="admin")
    new: dict[str, Any] = dict(
        username="admin", display_name="admin", kind="person", roles=["admin"], by="svc:a"
    )
    with open_uow(db) as u:
        accounts.create_account(u, password=word, **new)

    env = {
        "TL_DB": str(work / "t.db"),
        "TL_ENV": "dev",
        "TL_SESSION_FILE": str(work / "s.json"),
        "TL_OBJECT_ROOT": str(work / "objects"),
    }

    def tl(*args: str) -> tuple[int, str]:
        got = CliRunner().invoke(app, list(args), env=env, input=PW if args[0] == "login" else None)
        return got.exit_code, got.output

    code, _ = tl("login", "admin", "--password-stdin")
    ok(code == 0, "the admin signs in")

    code, out = tl("load", "loaders")
    listed = all(s in out for s in ("awp-wbs", "awp_wbs", "awp-cwa", "awp_cwa"))
    ok(code == 0 and listed, "loaders listed")

    def open_extract_plan(name: str, loader: str) -> tuple[int, int]:
        code, out = tl(
            "load", "open", str(SAMPLES / name), "--project", PROJECT, "--loader", loader
        )
        opened = OPENED.search(out)
        ok(code == 0 and opened is not None, f"{name} opened with {loader}")
        assert opened is not None
        run = opened.group(1)
        code, out = tl("load", "extract", run, "--project", PROJECT)
        ok(code == 0, f"{name} extracts")
        code, out = tl("load", "profile", run, "--project", PROJECT)
        ok(code == 0, f"{name} profiles")
        code, out = tl("load", "plan", run, "--project", PROJECT)
        counts = PLANNED.search(out)
        assert code == 0 and counts is not None, out
        return int(counts[1]), int(counts[3])

    new_wbs, invalid_wbs = open_extract_plan("wbs-sample.csv", "awp-wbs")
    ok(new_wbs == 12 and invalid_wbs == 1, f"plan new {new_wbs} invalid {invalid_wbs}")

    new_cwa, invalid_cwa = open_extract_plan("cwa-sample.csv", "awp-cwa")
    # 4 areas and the path they make (the path is a new record of the same plan, as in T02).
    what = f"cwa plan new {new_cwa} (4 areas and the path) invalid {invalid_cwa}"
    ok(new_cwa == 5 and invalid_cwa == 0, what)
    shipped = (SAMPLES / "wbs-sample.csv").is_file() and (SAMPLES / "cwa-sample.csv").is_file()
    ok(shipped, f"samples ship in the package at {SAMPLES}")
    print("T01 ok")


with tempfile.TemporaryDirectory() as tmp:
    main(Path(tmp))
