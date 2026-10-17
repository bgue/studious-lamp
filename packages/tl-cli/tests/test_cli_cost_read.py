"""`tl cost snapshots|codes|show` (P1-I4-T02b)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from xercli_support import Cast, P, tl, xer_env

AUTO_SIGN_IN = False
FIRST = (
    "code,description,parent,uom,hours_budget,hours_actual,"
    "amount_budget,amount_actual,amount_eac\n"
    "4210,Piping,,,1000,400.5,80000,30000,95000\n"
    "4210-PIP,Pipe installation,4210,in-dia,600,,,,\n"
    "4210-WLD,Welding,4210,,400,150,,,\n"
)
SECOND = """code,description,hours_budget,hours_actual
4210-PIP,Pipe installation (revised),600,250
4210-WLD,Welding,400,200
"""
THIRD = """code,description,hours_budget,hours_actual
4210-PIP,Pipe installation (revised),600,260
"""


@pytest.fixture
def cast(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cast:
    return Cast(xer_env(new_db, monkeypatch, tmp_path), tmp_path)


def imported(cast: Cast, tmp_path: Path) -> None:
    """July (three codes, in USD), August (two of them revised) and a corrected August file (the
    next revision, `2026-08@2`), as the admin."""
    for name, body, period, as_of, extra in (
        ("a.csv", FIRST, "2026-07", "2026-07-31", ("--currency", "USD")),
        ("b.csv", SECOND, "2026-08", "2026-08-31", ()),
        ("c.csv", THIRD, "2026-08", "2026-08-31", ()),
    ):
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        tl(
            cast.boss, "cost", "import", str(path), *P,
            "--period", period, "--as-of", as_of, *extra, "--apply", ok=True,
        )  # fmt: skip


def lines(cast: Cast, *args: str) -> list[str]:
    """What a plain user (who may only read) sees for one command."""
    return tl(cast.ursula, "cost", *args, ok=True).stdout.splitlines()


# --- snapshots ----------------------------------------------------------------------------------


def test_snapshots_says_so_when_nothing_was_imported(cast: Cast) -> None:
    assert lines(cast, "snapshots", *P) == ["no cost snapshots in project P123"]


def test_snapshots_lists_the_periods_newest_first(cast: Cast, tmp_path: Path) -> None:
    imported(cast, tmp_path)
    assert lines(cast, "snapshots", *P) == [
        "2026-08@2  as of 2026-08-31  rows 1  new 0  revised 0  -  c.csv",
        "2026-08@1  as of 2026-08-31  rows 2  new 0  revised 1  -  b.csv",
        "2026-07@1  as of 2026-07-31  rows 3  new 3  revised 0  USD  a.csv",
    ]
    assert lines(cast, "snapshots", "--project", "P999") == ["no cost snapshots in project P999"]


# --- codes --------------------------------------------------------------------------------------


def test_codes_lists_every_code_with_its_latest_amounts(cast: Cast, tmp_path: Path) -> None:
    imported(cast, tmp_path)
    assert lines(cast, "codes", *P) == [
        "cost codes: 3",
        "4210  level 1  uom -  budget 80,000.00  actual 30,000.00  eac 95,000.00  Piping",
        "4210-PIP  level 2  uom in-dia  budget -  actual -  eac -  Pipe installation (revised)",
        "4210-WLD  level 2  uom -  budget -  actual -  eac -  Welding",
    ]


def test_codes_filters_by_parent_and_by_text_and_cuts_at_the_limit(
    cast: Cast, tmp_path: Path
) -> None:
    imported(cast, tmp_path)
    children = lines(cast, "codes", *P, "--parent", "4210")
    assert children[0] == "cost codes: 2"
    assert [x.split()[0] for x in children[1:]] == ["4210-PIP", "4210-WLD"]
    assert [x.split()[0] for x in lines(cast, "codes", *P, "--search", "WELD")[1:]] == ["4210-WLD"]
    # the title "Piping" holds "pip" too: the search looks at the code and the title
    found = lines(cast, "codes", *P, "--search", "pip")
    assert [x.split()[0] for x in found[1:]] == ["4210", "4210-PIP"]
    assert lines(cast, "codes", *P, "--search", "nothing like this") == ["cost codes: 0"]
    assert lines(cast, "codes", *P, "--limit", "1")[0] == "cost codes: 1"
    assert tl(cast.ursula, "cost", "codes", *P, "--limit", "0").exit_code == 2
    assert lines(cast, "codes", "--project", "P999") == ["cost codes: 0"]


# --- show ---------------------------------------------------------------------------------------


def test_show_prints_a_code_with_its_figures_and_what_each_snapshot_said(
    cast: Cast, tmp_path: Path
) -> None:
    imported(cast, tmp_path)
    assert lines(cast, "show", "4210-PIP", *P) == [
        "cost code 4210-PIP",
        "title Pipe installation (revised)",
        "parent 4210",
        "level 2",
        "uom in-dia",
        "active yes",
        "children -",
        "figures from 2026-08 as of 2026-08-31",
        "hours  budget 600.00  actual 260.00  earned -  ftc -  eac -",
        "quantity  budget -  actual -  earned -  ftc -  eac -",
        "amount  budget -  actual -  earned -  ftc -  eac -",
        "history 3",
        "  2026-07@1  as of 2026-07-31  amount budget -  actual -  eac -  hours actual -",
        "  2026-08@1  as of 2026-08-31  amount budget -  actual -  eac -  hours actual 250.00",
        "  2026-08@2  as of 2026-08-31  amount budget -  actual -  eac -  hours actual 260.00",
    ]


def test_show_a_parent_lists_its_children_and_thousands_separators(
    cast: Cast, tmp_path: Path
) -> None:
    imported(cast, tmp_path)
    assert lines(cast, "show", "4210", *P) == [
        "cost code 4210",
        "title Piping",
        "parent -",
        "level 1",
        "uom -",
        "active yes",
        "children 4210-PIP, 4210-WLD",
        "figures from 2026-07 as of 2026-07-31",
        "hours  budget 1,000.00  actual 400.50  earned -  ftc -  eac -",
        "quantity  budget -  actual -  earned -  ftc -  eac -",
        "amount  budget 80,000.00  actual 30,000.00  earned -  ftc -  eac 95,000.00",
        "history 1",
        "  2026-07@1  as of 2026-07-31  amount budget 80,000.00  actual 30,000.00  "
        "eac 95,000.00  hours actual 400.50",
    ]


def test_show_says_when_a_code_is_no_longer_active(cast: Cast, tmp_path: Path) -> None:
    imported(cast, tmp_path)
    with open_uow(cast.target) as uow:
        uow.conn().execute(
            text("UPDATE cur_cost_costcode SET is_active = :off WHERE code = '4210-WLD'"),
            {"off": False},
        )
    assert lines(cast, "show", "4210-WLD", *P)[5] == "active no"
    assert lines(cast, "show", "4210-PIP", *P)[5] == "active yes"


def test_show_a_code_that_is_not_there_is_an_error_not_a_trace(cast: Cast, tmp_path: Path) -> None:
    imported(cast, tmp_path)
    missing = tl(cast.ursula, "cost", "show", "NOPE", *P, ok=False)
    assert "error: no cost code 'NOPE' in project:P123" in missing.output
    other = tl(cast.ursula, "cost", "show", "4210", "--project", "P999", ok=False)
    assert "error: no cost code '4210' in project:P999" in other.output


# --- reads write nothing ------------------------------------------------------------------------


def test_no_read_writes_to_the_ledger(cast: Cast, tmp_path: Path) -> None:
    imported(cast, tmp_path)

    def count() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    before = count()
    for command in (("snapshots", *P), ("codes", *P), ("show", "4210", *P)):
        lines(cast, *command)
    assert count() == before
