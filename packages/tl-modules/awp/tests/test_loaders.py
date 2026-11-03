"""The loaders awp-wbs and awp-cwa and their sample files (T01): counts from the shipped samples."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

import pytest
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_mod_awp.loaders.awp import cwa_loader, wbs_loader
from tl_mod_cost.testing import CostWorld, row
from typer.testing import CliRunner

PW = "correct horse battery"
SAMPLES = Path(str(files("tl_mod_awp") / "samples"))
OPENED = re.compile(r"opened (\S+)")
PLANNED = re.compile(r"planned \S+ new (\d+) existing (\d+) invalid (\d+)")


@pytest.fixture
def tl(tmp_path: Path):  # type: ignore[no-untyped-def]
    db = as_target(str(tmp_path / "t.db"))
    create_schema(db)
    CostWorld(db).import_snapshot([row(c, c) for c in ("WLD", "ERC", "TST")])
    with open_uow(db) as u:
        accounts.create_account(
            u,
            username="admin",
            display_name="admin",
            kind="person",
            roles=["admin"],
            by="svc:a",
            password=prepare_password(PW, username="admin"),
        )
    env = {
        "TL_DB": str(tmp_path / "t.db"),
        "TL_ENV": "dev",
        "TL_SESSION_FILE": str(tmp_path / "s.json"),
        "TL_OBJECT_ROOT": str(tmp_path / "objects"),
    }

    def run(*args: str) -> tuple[int, str]:
        got = CliRunner().invoke(app, list(args), env=env, input=PW if args[0] == "login" else None)
        return got.exit_code, got.output

    assert run("login", "admin", "--password-stdin")[0] == 0
    return run


def _plan(tl, name: str, loader: str) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    code, out = tl("load", "open", str(SAMPLES / name), "--project", "P123", "--loader", loader)
    opened = OPENED.search(out)
    assert code == 0
    assert opened is not None
    run = opened.group(1)
    for step in ("extract", "profile"):
        assert tl("load", step, run, "--project", "P123")[0] == 0
    code, out = tl("load", "plan", run, "--project", "P123")
    counts = PLANNED.search(out)
    assert code == 0
    assert counts is not None, out
    return int(counts[1]), int(counts[2]), int(counts[3])


def test_the_loaders_are_listed(tl) -> None:  # type: ignore[no-untyped-def]
    code, out = tl("load", "loaders")
    assert code == 0
    for word in ("awp-wbs", "awp_wbs", "awp-cwa", "awp_cwa"):
        assert word in out


def test_the_wbs_sample_plans_12_new_and_1_invalid(tl) -> None:  # type: ignore[no-untyped-def]
    assert _plan(tl, "wbs-sample.csv", "awp-wbs") == (12, 0, 1)


def test_the_cwa_sample_plans_5_new_4_areas_and_the_path(tl) -> None:  # type: ignore[no-untyped-def]
    assert _plan(tl, "cwa-sample.csv", "awp-cwa") == (5, 0, 0)


def test_the_loader_definitions_name_their_targets_and_ship_a_mapping() -> None:
    for loader, target, table in (
        (wbs_loader(), "awp_wbs", "wbs"),
        (cwa_loader(), "awp_cwa", "cwa"),
    ):
        assert loader.target == target
        assert loader.table == table
        assert loader.system == "awp"
        assert loader.file_types == ("csv", "xlsx")
        assert loader.mapping_text.strip()


def test_the_samples_ship_inside_the_package() -> None:
    assert (SAMPLES / "wbs-sample.csv").is_file()
    assert (SAMPLES / "cwa-sample.csv").is_file()
    wbs = (SAMPLES / "wbs-sample.csv").read_text(encoding="utf-8").splitlines()
    assert len(wbs) == 14  # the header and 13 rows
    cwa = (SAMPLES / "cwa-sample.csv").read_text(encoding="utf-8").splitlines()
    assert len(cwa) == 5  # the header and 4 areas
