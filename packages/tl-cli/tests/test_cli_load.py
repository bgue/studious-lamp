"""`tl load ...`: legacy loader runs from the command line (P1-I8, plumbing)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from auth_support import run as tl
from derivecli_support import as_admin, derive_env, sign_in_as
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_mod_legacy.model import use_loaders
from tl_mod_legacy.testing import LegacyWorld, tag_csv, tag_loader
from typer.testing import Result as RunResult


@pytest.fixture(autouse=True)
def loaders() -> Iterator[None]:
    with use_loaders({"test-tags": tag_loader()}):
        yield


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    values["TL_LAKE_DIR"] = str(tmp_path / "lake")
    LegacyWorld(as_target(values["TL_DB"]), tmp_path / "unused").load_standards()
    return values


def load(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "load", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def csv_file(tmp_path: Path, count: int = 6, name: str = "index.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(tag_csv(count))
    return path


def test_a_run_goes_from_the_file_to_the_reconciliation_and_back(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    assert load(env, "loaders").stdout.startswith("test-tags  plantx/tags  tags  csv,xlsx  ")
    opened = load(
        env, "open", str(csv_file(tmp_path)), "--project", "P123", "--loader", "test-tags"
    )
    assert opened.stdout.startswith("opened plantx/tags#1 ")
    run = "plantx/tags#1"
    assert load(env, "extract", run, "--project", "P123").stdout.strip() == (
        "extracted plantx/tags#1 rows 6 columns 11"
    )
    assert load(env, "profile", run, "--project", "P123").stdout.strip() == "profiled plantx/tags#1"
    shown = load(env, "profile", run, "--project", "P123", "--show").stdout.splitlines()
    assert shown[0] == "rows 6  duplicate rows 0"
    assert any(line.startswith("TAG NO") and "key-candidate" in line for line in shown)
    assert load(env, "plan", run, "--project", "P123").stdout.strip() == (
        "planned plantx/tags#1 new 6 existing 0 invalid 0"
    )
    loaded = load(env, "load", run, "--project", "P123", "--expect-new", "6").stdout
    assert loaded.startswith(
        "loaded plantx/tags#1 created 6 existing 0 invalid 0 correlation load:"
    )
    reconciled = load(env, "reconcile", run, "--project", "P123").stdout.strip()
    assert reconciled == "reconciled plantx/tags#1 matched 6 mismatches 0 left-alone-that-differ 0"
    listed = load(env, "ls", "--project", "P123").stdout.splitlines()
    assert listed == ["plantx/tags#1  Reconciled  test-tags  index.csv"]
    details = load(env, "show", run, "--project", "P123").stdout
    assert "state Reconciled" in details and "loaded 6" in details
    assert '"mismatches": 0' in load(env, "show", run, "--project", "P123", "--report").stdout
    undone = load(env, "compensate", run, "--project", "P123", "--reason", "wrong file").stdout
    assert undone.strip() == "compensated plantx/tags#1 reversed 6"


def test_a_stale_plan_and_an_unknown_loader_are_one_error_line(
    env: dict[str, str], tmp_path: Path
) -> None:
    as_admin(env)
    bad = load(
        env, "open", str(csv_file(tmp_path)), "--project", "P123", "--loader", "nope", ok=False
    )
    assert "error: no loader 'nope' (installed: test-tags)" in bad.output
    load(env, "open", str(csv_file(tmp_path)), "--project", "P123", "--loader", "test-tags")
    early = load(env, "load", "plantx/tags#1", "--project", "P123", ok=False)
    assert "error: plantx/tags#1 is Opened: load needs Planned" in early.output
    refused = load(
        env, "compensate", "plantx/tags#9", "--project", "P123", "--reason", "x", ok=False
    )
    assert "no load run" in refused.output


def test_every_command_is_the_administrators(env: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs every Postgres command in as one admin")
    as_admin(env)
    plain = sign_in_as(env, tmp_path, "plain", ["user"])
    path = csv_file(tmp_path)
    for args in (
        ("open", str(path), "--project", "P123", "--loader", "test-tags"),
        ("ls", "--project", "P123"),
        ("show", "plantx/tags#1", "--project", "P123"),
        ("extract", "plantx/tags#1", "--project", "P123"),
    ):
        denied = load(plain, *args, ok=False)
        assert "forbidden" in denied.output, args
