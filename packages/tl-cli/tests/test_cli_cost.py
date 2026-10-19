"""`tl cost import`: preview and apply one period of cost figures (P1-I4)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from xercli_support import Cast, P, tl, xer_env

AUTO_SIGN_IN = False
JULY = ("--period", "2026-07", "--as-of", "2026-07-31")
FIRST = """code,description,parent,uom,hours_budget,hours_actual,amount_budget
4210,Piping,,,1000,400.5,80000
4210-PIP,Pipe installation,4210,in-dia,600,,
4210-WLD,Welding,4210,,400,150,
"""
SECOND = """code,description,hours_budget,hours_actual
4210-PIP,Pipe installation (revised),600,250
4210-WLD,Welding,400,200
"""


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    return xer_env(new_db, monkeypatch, tmp_path)


@pytest.fixture
def cast(env: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(env, tmp_path)


def csv(tmp_path: Path, body: str, name: str = "cost.csv") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def count(cast: Cast, sql: str) -> int:
    with open_uow(cast.target, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_the_preview_writes_nothing_and_any_signed_in_person_may_read_it(
    cast: Cast, tmp_path: Path
) -> None:
    out = tl(cast.ursula, "cost", "import", csv(tmp_path, FIRST), *P, *JULY, ok=True).stdout
    lines = out.splitlines()
    assert lines[0] == "import cost.csv into project P123 as 2026-07 (as of 2026-07-31)"
    assert lines[1] == "new=3  revised=0  unchanged=0"
    assert lines[2:5] == [
        "+ 4210  level 1  Piping",
        "+ 4210-PIP  level 2  Pipe installation",
        "+ 4210-WLD  level 2  Welding",
    ]
    assert lines[-1] == "dry run: nothing written; add --apply to write"
    assert count(cast, "SELECT COUNT(*) FROM cur_cost_costcode") == 0


def test_applying_is_the_admins_and_nobody_elses(cast: Cast, tmp_path: Path) -> None:
    path = csv(tmp_path, FIRST)
    for who in (cast.ursula, cast.dora):
        refused = tl(who, "cost", "import", path, *P, *JULY, "--apply", ok=False)
        assert "needs the admin role" in refused.output
    assert count(cast, "SELECT COUNT(*) FROM cur_cost_costcode") == 0
    done = tl(cast.boss, "cost", "import", path, *P, *JULY, "--apply", ok=True).stdout
    assert done.splitlines()[-1] == "applied 2026-07@1: codes=3  new=3  revised=0"
    assert count(cast, "SELECT COUNT(*) FROM cur_cost_costcode") == 3
    assert count(cast, "SELECT COUNT(*) FROM cur_cost_snapshot_value") == 3


def test_a_second_period_shows_what_is_revised_and_a_corrected_file_is_the_next_revision(
    cast: Cast, tmp_path: Path
) -> None:
    tl(cast.boss, "cost", "import", csv(tmp_path, FIRST), *P, *JULY, "--apply", ok=True)
    august = ("--period", "2026-08", "--as-of", "2026-08-31")
    preview = tl(
        cast.boss, "cost", "import", csv(tmp_path, SECOND, "aug.csv"), *P, *august, ok=True
    )
    lines = preview.stdout.splitlines()
    assert lines[1] == "new=0  revised=1  unchanged=1"
    assert lines[2] == "~ 4210-PIP  title: Pipe installation -> Pipe installation (revised)"
    tl(
        cast.boss,
        "cost",
        "import",
        csv(tmp_path, SECOND, "aug.csv"),
        *P,
        *august,
        "--apply",
        ok=True,
    )
    again = tl(
        cast.boss,
        "cost",
        "import",
        csv(tmp_path, SECOND, "aug2.csv"),
        *P,
        *august,
        "--apply",
        ok=True,
    ).stdout
    assert again.splitlines()[-1].startswith("applied 2026-08@2:")


def test_a_bad_file_is_named_by_its_fixed_message_and_nothing_is_written(
    cast: Cast, tmp_path: Path
) -> None:
    for body, message in (
        ("description\nPiping\n", "the file has no code column"),
        ("code,hours_budget\n4210,1e5\n", "row 1: hours_budget is not a plain number"),
        ("code\n4210\n4210\n", "4210: the code appears twice"),
        ("code,parent\n4210-PIP,4210\n", "the parent 4210 is neither in the file nor a known code"),
        ("", "the file is empty"),
    ):
        out = tl(cast.boss, "cost", "import", csv(tmp_path, body), *P, *JULY, "--apply", ok=False)
        assert message in out.output, (body, out.output)
    assert count(cast, "SELECT COUNT(*) FROM cur_cost_costcode") == 0
    future = tl(
        cast.boss, "cost", "import", csv(tmp_path, FIRST), *P, "--period", "2036-01",
        "--as-of", "2036-01-31", "--apply", ok=False,
    )  # fmt: skip
    assert "is in the future" in future.output
    badperiod = tl(
        cast.boss, "cost", "import", csv(tmp_path, FIRST), *P, "--period", "2026-13",
        "--as-of", "2026-07-31", ok=False,
    )  # fmt: skip
    assert "period must be written YYYY-MM" in badperiod.output


def test_a_file_over_the_limit_is_refused_before_it_is_read(
    cast: Cast, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tl_cli.cost.MAX_IMPORT_BYTES", 10)
    out = tl(cast.boss, "cost", "import", csv(tmp_path, FIRST), *P, *JULY, ok=False)
    assert "a cost export may be at most 10" in out.output


def test_the_import_command_has_the_hooked_actor_option(tmp_path: Path) -> None:
    import typer.main
    from tl_cli import actor_hook
    from tl_cli.main import app

    root = typer.main.get_command(app)
    actor_hook.install(root, tmp_path / "x.db")
    command = root.commands["cost"].commands["import"]  # type: ignore[attr-defined]
    assert any("--actor" in getattr(p, "opts", []) for p in command.params)
