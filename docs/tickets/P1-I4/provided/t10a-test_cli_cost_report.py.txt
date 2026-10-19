"""`tl cost report budget|uncoded` (P1-I4-T10a)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import CreateRecord
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import handle_create_record
from xercli_support import Cast, P, tl, xer_env

AUTO_SIGN_IN = False
CSV = """code,description,parent,uom,quantity_budget,quantity_actual,quantity_eac,hours_budget
4210,Piping,,,1000,400,1100,50
4210-PIP,Pipe installation,4210,in-dia,600,450,600,
4210-WLD,Welding,4210,,0,5,,
4220,Supports,,,,,,
"""


@pytest.fixture
def cast(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Cast:
    return Cast(xer_env(new_db, monkeypatch, tmp_path), tmp_path)


def code_id(cast: Cast, code: str) -> str:
    with open_uow(cast.target, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT id FROM cur_cost_costcode WHERE code = :c"), {"c": code}
        )
        return str(found.scalar_one())


def loaded(cast: Cast, tmp_path: Path) -> None:
    """Four cost codes (July), and four records: REC-1 linked to 4210-PIP, REC-2 to 4210-PIP and
    4210, REC-3 and REC-4 to nothing."""
    path = tmp_path / "cost.csv"
    path.write_text(CSV, encoding="utf-8")
    tl(
        cast.boss, "cost", "import", str(path), *P,
        "--period", "2026-07", "--as-of", "2026-07-31", "--apply", ok=True,
    )  # fmt: skip
    ids: dict[str, str] = {}
    for key in ("REC-1", "REC-2", "REC-3", "REC-4"):
        with open_uow(cast.target) as uow:
            made = handle_create_record(
                uow,
                CreateRecord(
                    actor="user:ursula", source="test", scope="project:P123",
                    record_type="core.Record", title=f"Record {key[-1]}", key=key,
                ),
            )  # fmt: skip
        ids[key] = made.stream_id
    for key, code in (("REC-1", "4210-PIP"), ("REC-2", "4210-PIP"), ("REC-2", "4210")):
        with open_uow(cast.target) as uow:
            handle_add_link(
                uow,
                AddLink(
                    actor="user:ursula", source="test", scope="project:P123",
                    from_id=ids[key], to_id=code_id(cast, code), relation="references",
                ),
            )  # fmt: skip


def lines(cast: Cast, *args: str) -> list[str]:
    """What a plain user (who may only read) sees for one command."""
    return tl(cast.ursula, "cost", "report", *args, ok=True).stdout.splitlines()


# --- budget -------------------------------------------------------------------------------------


def test_budget_judges_each_code_on_one_unit(cast: Cast, tmp_path: Path) -> None:
    loaded(cast, tmp_path)
    assert lines(cast, "budget", *P) == [
        "budget report (quantity): 4 codes, 1 over budget",
        "4210  level 1  uom -  budget 1,000.00  actual 400.00  eac 1,100.00  variance -100.00  "
        "spent 40.0%  linked 1  over  Piping",
        "4210-PIP  level 2  uom in-dia  budget 600.00  actual 450.00  eac 600.00  variance 0.00  "
        "spent 75.0%  linked 2  ok  Pipe installation",
        "4210-WLD  level 2  uom -  budget 0.00  actual 5.00  eac -  variance -  spent -  "
        "linked 0  ok  Welding",
        "4220  level 1  uom -  budget -  actual -  eac -  variance -  spent -  linked 0  ok  "
        "Supports",
    ]


def test_budget_takes_a_unit_a_parent_and_a_limit(cast: Cast, tmp_path: Path) -> None:
    loaded(cast, tmp_path)
    hours = lines(cast, "budget", *P, "--unit", "hours")
    assert hours[0] == "budget report (hours): 4 codes, 0 over budget"
    assert hours[1].startswith("4210  level 1  uom -  budget 50.00  actual -  eac -  variance -")
    amount = lines(cast, "budget", *P, "--unit", "amount")
    assert amount[0] == "budget report (amount): 4 codes, 0 over budget"
    children = lines(cast, "budget", *P, "--parent", "4210")
    assert children[0] == "budget report (quantity): 2 codes, 0 over budget"
    assert [x.split()[0] for x in children[1:]] == ["4210-PIP", "4210-WLD"]
    assert [x.split()[0] for x in lines(cast, "budget", *P, "--limit", "1")[1:]] == ["4210"]
    assert tl(cast.ursula, "cost", "report", "budget", *P, "--limit", "0").exit_code == 2


def test_budget_over_keeps_the_codes_whose_forecast_exceeds_the_budget(
    cast: Cast, tmp_path: Path
) -> None:
    loaded(cast, tmp_path)
    over = lines(cast, "budget", *P, "--over")
    assert over[0] == "budget report (quantity): 1 codes, 1 over budget"
    assert [x.split()[0] for x in over[1:]] == ["4210"]


def test_budget_refuses_another_unit_and_sees_only_its_own_project(
    cast: Cast, tmp_path: Path
) -> None:
    loaded(cast, tmp_path)
    refused = tl(cast.ursula, "cost", "report", "budget", *P, "--unit", "money", ok=False)
    assert "error: unit must be one of hours, quantity, amount" in refused.output
    assert lines(cast, "budget", "--project", "P999") == [
        "budget report (quantity): 0 codes, 0 over budget"
    ]


# --- uncoded ------------------------------------------------------------------------------------


def test_uncoded_lists_the_records_with_no_cost_code_by_key(cast: Cast, tmp_path: Path) -> None:
    loaded(cast, tmp_path)
    [head, third, fourth] = lines(cast, "uncoded", *P, "--type", "core.Record")
    assert head == "records without a cost code (core.Record): 2"
    assert third.startswith("REC-3  ") and third.endswith("  Record 3")
    assert fourth.startswith("REC-4  ") and fourth.endswith("  Record 4")
    assert len(third.split()[1]) == 26


def test_uncoded_takes_a_type_and_a_limit_and_sees_only_its_own_project(
    cast: Cast, tmp_path: Path
) -> None:
    loaded(cast, tmp_path)
    assert lines(cast, "uncoded", *P, "--type", "core.Other") == [
        "records without a cost code (core.Other): 0"
    ]
    one = lines(cast, "uncoded", *P, "--type", "core.Record", "--limit", "1")
    assert one[0].endswith("): 1") and one[1].startswith("REC-3  ")
    assert lines(cast, "uncoded", "--project", "P999", "--type", "core.Record")[0].endswith("): 0")
    assert (
        tl(cast.ursula, "cost", "report", "uncoded", *P, ok=False).exit_code == 2
    )  # --type is required


# --- reads write nothing ------------------------------------------------------------------------


def test_no_report_writes_to_the_ledger(cast: Cast, tmp_path: Path) -> None:
    loaded(cast, tmp_path)

    def count() -> int:
        with open_uow(cast.target, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())

    before = count()
    lines(cast, "budget", *P)
    lines(cast, "uncoded", *P, "--type", "core.Record")
    assert count() == before
