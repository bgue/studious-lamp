"""The Commercial export to the cost system: pending and approved, classes, quoting (P1-I6-S5)."""

from __future__ import annotations

import csv
import io

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_mod_correspondence import export as ex
from tl_mod_correspondence.errors import ExportClassError
from tl_mod_correspondence.testing import (
    CONTROLLER,
    PROJECT,
    CorrWorld,
    as_controller,
    frozen_today,
)

TODAY = "2026-10-30"
PLAIN = cf.Viewer(actor="user:bob", level=0, account="user:bob")


def export(
    world: CorrWorld, viewer: cf.Viewer = CONTROLLER, classes: tuple[str, ...] = ("restricted",)
) -> ex.ExportResult:
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        return ex.commercial_export(uow.conn(), PROJECT, classes=classes, today=TODAY)


def by_number(result: ex.ExportResult) -> dict[str, dict[str, str]]:
    return {row[0]: dict(zip(ex.COLUMNS, row, strict=True)) for row in result.rows}


def test_only_what_was_given_to_the_other_party_is_a_change(world: CorrWorld) -> None:
    for number, state in (
        ("P123-EW-0001", "Draft"),
        ("P123-EW-0002", "Commercial review"),
        ("P123-EW-0003", "PM approval"),
        ("P123-EW-0004", "Awaiting assessment"),
        ("P123-EW-0005", "Agreed"),
        ("P123-EW-0006", "Disputed"),
        ("P123-EW-0007", "Partially agreed"),
        ("P123-EW-0008", "Escalated"),
        ("P123-EW-0009", "Closed"),
    ):
        world.forge_commercial(number, state=state)
    world.forge_commercial("P123-EW-0010", state="Draft")
    with as_controller(), frozen_today("2026-10-20"):
        world.void_draft(world.item("P123-EW-0010").id)
    found = by_number(export(world))
    assert {n: r["cost_status"] for n, r in found.items()} == {
        "P123-EW-0004": "pending",
        "P123-EW-0005": "approved",
        "P123-EW-0006": "pending",
        "P123-EW-0007": "approved",
        "P123-EW-0008": "pending",
        "P123-EW-0009": "approved",  # agreed, then closed: still an approved change
    }


def test_the_value_is_the_assessed_one_for_an_approved_change_and_the_estimate_otherwise(
    world: CorrWorld,
) -> None:
    world.forge_commercial("P123-CN-0001", state="Awaiting assessment", estimated_value="500.00")
    world.forge_commercial("P123-CN-0002", state="Agreed", estimated_value="500.00")
    world.forge_commercial("P123-CN-0003", state="Disputed", estimated_value="700.00")
    found = by_number(export(world))
    assert (found["P123-CN-0001"]["value"], found["P123-CN-0001"]["value_basis"]) == (
        "500.00",
        "estimated",
    )
    assert (found["P123-CN-0002"]["value"], found["P123-CN-0002"]["value_basis"]) == (
        "9000.00",
        "assessed",
    )
    assert (found["P123-CN-0003"]["value"], found["P123-CN-0003"]["value_basis"]) == (
        "700.00",
        "estimated",
    )


def test_a_row_carries_the_columns_in_order(world: CorrWorld) -> None:
    clause = world.clause("CT-1", "20.1")
    rfi = world.forge_technical("P123-RFI-0001", state="Answered")
    world.forge_commercial(
        "P123-CN-0004",
        subject="Change: re-routing",
        subtype="change_notice",
        state="Awaiting assessment",
        issued_on="2026-10-21",
        contract_clause_id=clause.stream_id,
        derived_from_id=rfi,
        currency="USD",
        estimated_value="12500.00",
        estimated_hours="240.5",
        schedule_impact_days=-3,
        cost_code_impacts=[
            {
                "cost_code": "2.3.1",
                "amount": "10000.00",
                "hours": None,
                "quantity": None,
                "uom": None,
            },
            {"cost_code": "2.3.2", "amount": None, "hours": "12.0", "quantity": None, "uom": None},
        ],
        aware_on="2026-10-19",
    )
    [row] = export(world).rows
    assert dict(zip(ex.COLUMNS, row, strict=True)) == {
        "number": "P123-CN-0004",
        "kind": "change_notice",
        "title": "Change: re-routing",
        "cost_status": "pending",
        "state": "Awaiting assessment",
        "currency": "USD",
        "value": "12500.00",
        "value_basis": "estimated",
        "hours": "240.5",
        "schedule_impact_days": "-3",
        "cost_codes": "2.3.1=10000.00;2.3.2",
        "clause": "CT-1/20.1",
        "aware_on": "2026-10-19",
        "issued_on": "2026-10-21",
        "time_bar_due": "",
        "time_bar_late": "no",
        "source_rfi": "P123-RFI-0001",
        "class": "restricted",
    }


def test_the_time_bar_columns(world: CorrWorld) -> None:
    item = world.forge_commercial("P123-EW-0001", state="Awaiting assessment")
    with as_controller(), frozen_today("2026-10-01"):
        world.start_clock(
            item, label="Time bar", kind="time_bar", duration_days=14, start_on="2026-10-01"
        )
    [row] = export(world).rows
    found = dict(zip(ex.COLUMNS, row, strict=True))
    assert (found["time_bar_due"], found["time_bar_late"]) == ("2026-10-15", "yes")


def test_the_default_class_is_internal_and_the_restricted_items_are_counted_not_written(
    world: CorrWorld,
) -> None:
    world.forge_commercial("P123-EW-0001", state="Agreed")
    world.forge_commercial("P123-EW-0002", state="Agreed", confidentiality="internal")
    quiet = export(world, classes=("internal",))
    assert [row[0] for row in quiet.rows] == ["P123-EW-0002"]
    assert quiet.left_out == {"restricted": 1}
    loud = export(world, classes=("internal", "restricted"))
    assert sorted(row[0] for row in loud.rows) == ["P123-EW-0001", "P123-EW-0002"]
    assert loud.left_out == {}


def test_restricted_needs_a_controller_and_privileged_is_never_exported(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", state="Agreed")
    with pytest.raises(ForbiddenError, match="document_controller"):
        export(world, viewer=PLAIN, classes=("restricted",))
    with pytest.raises(ExportClassError, match="never exported"):
        export(world, classes=("internal", "privileged"))
    with pytest.raises(ExportClassError, match="unknown class"):
        export(world, classes=("secret",))
    assert export(world, viewer=PLAIN, classes=("internal",)).rows == []


def test_what_the_viewer_may_not_read_is_neither_written_nor_counted(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", state="Agreed", confidentiality="privileged")
    world.forge_commercial("P123-EW-0002", state="Agreed", confidentiality="Secret")
    world.forge_commercial("P123-EW-0003", state="Agreed")
    quiet = export(world, classes=("internal",))
    assert quiet.rows == [] and quiet.left_out == {"restricted": 1}
    assert [row[0] for row in export(world).rows] == ["P123-EW-0003"]
    plain = export(world, viewer=PLAIN, classes=("internal",))
    assert plain.rows == [] and plain.left_out == {}  # a plain viewer reads none of them


def test_a_text_a_spreadsheet_would_run_is_written_with_a_leading_quote(world: CorrWorld) -> None:
    world.forge_commercial(
        "P123-EW-0001",
        subject='=HYPERLINK("http://x")',
        state="Agreed",
        cost_code_impacts=[
            {"cost_code": "=1+1", "amount": "5.00", "hours": None, "quantity": None, "uom": None}
        ],
        entitlement_basis="+cmd",
    )
    world.forge_commercial("P123-EW-0002", subject="@sum", state="Agreed")
    world.forge_commercial("P123-EW-0003", subject="-1+2", state="Agreed")
    world.forge_commercial("P123-EW-0004", subject="|calc", state="Agreed")
    text = ex.csv_text(export(world))
    rows = {r["number"]: r for r in csv.DictReader(io.StringIO(text))}
    assert rows["P123-EW-0001"]["title"] == '\'=HYPERLINK("http://x")'
    assert rows["P123-EW-0001"]["cost_codes"] == "'=1+1=5.00"
    assert rows["P123-EW-0002"]["title"] == "'@sum"
    assert rows["P123-EW-0003"]["title"] == "'-1+2"
    assert rows["P123-EW-0004"]["title"] == "'|calc"


def test_a_plain_number_is_not_quoted() -> None:
    assert ex.safe_cell("-3") == "-3" and ex.safe_cell("12500.00") == "12500.00"
    assert ex.safe_cell("-3x") == "'-3x" and ex.safe_cell(None) == ""
    assert ex.safe_cell("\tcmd") == "'\tcmd" and ex.safe_cell("\rcmd") == "'\rcmd"


def test_the_csv_has_the_header_and_unix_line_ends(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", state="Agreed")
    text = ex.csv_text(export(world))
    assert text.splitlines()[0] == ",".join(ex.COLUMNS)
    assert "\r" not in text and text.endswith("\n") and len(text.splitlines()) == 2
    empty = ex.csv_text(ex.ExportResult(rows=[]))
    assert empty == ",".join(ex.COLUMNS) + "\n"


def test_another_project_is_not_exported(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", state="Agreed")
    world.forge_commercial("P999-EW-0001", state="Agreed", scope="project:P999")
    assert [row[0] for row in export(world).rows] == ["P123-EW-0001"]


def test_no_float_arithmetic_touches_an_amount(world: CorrWorld) -> None:
    world.forge_commercial("P123-EW-0001", state="Awaiting assessment", estimated_value="0.10")
    [row] = export(world).rows
    assert dict(zip(ex.COLUMNS, row, strict=True))["value"] == "0.10"


def test_a_register_too_big_for_one_file_is_refused_not_cut_short(
    world: CorrWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ex, "MAX_ROWS", 2)
    for n in range(1, 4):
        world.forge_commercial(f"P123-EW-000{n}", state="Awaiting assessment")
    with pytest.raises(ExportClassError, match="more than 2"):
        export(world)
    monkeypatch.setattr(ex, "MAX_ROWS", 3)
    assert len(export(world).rows) == 3
