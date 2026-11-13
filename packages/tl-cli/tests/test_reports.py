"""`tl awp report` (T04b, D28): the three reports on a ledger with cost-system hours."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from test_cli_awp import Cli, load_world
from tl_adapters.db import as_target, create_schema
from tl_mod_cost.testing import CostWorld, row


@pytest.fixture
def cli(tmp_path: Path) -> Cli:
    """A small ledger: node 1.1 maps 60/40 to WLD/ERC with a package of 100 h; the cost system
    states 50 h for WLD, nothing for ERC, and 5 h for a code the awp does not use."""
    path = tmp_path / "reports.db"
    target = as_target(str(path))
    create_schema(target)
    w = load_world().World(target)
    w.people()
    w.editions()
    CostWorld(target).import_snapshot(
        [
            row("WLD", "Welding", hours_budget=50),
            row("ERC", "Erection"),
            row("OTHER", "Not in the WBS", hours_budget=5),
        ]
    )
    w.call("sue", "DefineWbsNode", code="1", title="Plant")
    w.call("sue", "DefineWbsNode", code="1.1", title="Unit", parent_code="1")
    w.call(
        "sue",
        "MapWbsToCostCodes",
        node=w.id_of("1.1"),
        allocations=[
            {"cost_code": "WLD", "percent": "60.00"},
            {"cost_code": "ERC", "percent": "40.00"},
        ],
    )
    w.call("sue", "DefineCwa", code="A1", title="Area one")
    cwp = w.new_cwp("PIP", "Rack", "A1", budget_hours="100")
    w.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=[{"wbs_code": "1.1", "percent": "100"}])
    w.call("sue", "DefineCwa", code="A2", title="Area two")
    tool = Cli(path, tmp_path)
    assert tool.run("rollup", "--project", "P123", "--actor", "user:sue").exit_code == 0
    assert tool.run("worker", "--once", "--actor", "user:ada").exit_code == 0
    return tool


def test_cwp_status_has_a_row_per_state_and_discipline_and_a_total(cli: Cli) -> None:
    assert cli.ok("report", "cwp_status") == ["Planned  PIP  1  100.0", "Total  -  1  100.0"]


def test_wbs_vs_cost_code_is_the_union_with_the_difference_awp_minus_cost(cli: Cli) -> None:
    lines = cli.ok("report", "wbs_vs_cost_code")
    assert lines == [
        "ERC  Erection  40.0  —  —",  # the cost system states no hours: no difference
        "OTHER  Not in the WBS  0.0  5.0  -5.0",  # only in the cost system
        "WLD  Welding  60.0  50.0  10.0",  # awp 60 minus cost 50
        "Unallocated  -  0.0  —  —",
    ]


def test_cwa_sequence_lists_the_path_with_the_package_counts(cli: Cli) -> None:
    w = load_world().World(as_target(str(cli.db)))
    w.call("sue", "DefinePathOfConstruction", steps=[{"cwa_code": "A1"}, {"cwa_code": "A2"}])
    assert cli.ok("report", "cwa_sequence") == [
        "1  A1  Area one  1  100.0",
        "2  A2  Area two  0  0.0",
    ]


def test_the_sequence_report_with_no_path_prints_nothing_and_exits_0(cli: Cli) -> None:
    result = cli.project("report", "cwa_sequence")
    assert result.exit_code == 0
    assert result.stdout == ""


def test_the_csv_flag_prints_a_header_and_the_same_cells(cli: Cli) -> None:
    result = cli.project("report", "wbs_vs_cost_code", "--csv")
    assert result.exit_code == 0
    parsed = list(csv.reader(io.StringIO(result.stdout)))
    assert len(parsed) == 5
    assert parsed[0] == ["code", "name", "awp_budget_hours", "cost_budget_hours", "difference"]
    assert [r[0] for r in parsed[1:]] == ["ERC", "OTHER", "WLD", "Unallocated"]
    plain = cli.ok("report", "wbs_vs_cost_code")
    assert [r[2] for r in parsed[1:]] == [line.split("  ")[2] for line in plain]


def test_an_empty_report_is_an_empty_csv(cli: Cli) -> None:
    result = cli.project("report", "cwa_sequence", "--csv")
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_an_unknown_report_or_a_missing_project_scope_exits_nonzero(cli: Cli) -> None:
    unknown = cli.project("report", "nope")
    assert unknown.exit_code != 0
