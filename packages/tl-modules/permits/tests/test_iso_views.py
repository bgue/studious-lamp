"""The isolation and gas test read views (P2-PTW T02). Every row of the ledger is made by a real
command. Red until T02 writes ``tl_mod_permits/iso_views.py`` (S3 left a stub).

Data: permits 1 (general, Approved) and 2 (hot work, Approved) and a hidden permit 3 (its record is
restricted); isolations 1 (Verified, linked to permits 1 and 3), 2 (Applied, free), 3 (Applied, its
point record is restricted), 4 (Removed); four gas tests of permit 2 and one of the hidden permit.
"""

from __future__ import annotations

import csv
import inspect
import io
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from permit_world import SCOPE, START, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_permits import iso_views
from tl_mod_permits.iso_views import (
    GAS_EXPORT_COLUMNS,
    ISOLATION_EXPORT_COLUMNS,
    GasRow,
    IsolationDetail,
    IsolationPage,
    IsolationRow,
    gas_export_rows,
    gas_tests_for,
    isolation_detail,
    isolation_export_rows,
    isolation_list,
)

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
POINT: dict[str, Any] = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}
Built = dict[str, str]  # name -> record id


def key(n: int) -> str:
    return f"P123-ISL-{n:04d}"


def lst(world: World, **kw: Any) -> IsolationPage:
    with open_uow(world.db, readonly=True) as uow:
        return isolation_list(uow.conn(), SCOPE, **kw)


def det(world: World, number: str, **kw: Any) -> IsolationDetail | None:
    with open_uow(world.db, readonly=True) as uow:
        return isolation_detail(uow.conn(), SCOPE, number, **kw)


def gas(world: World, permit: str, **kw: Any) -> list[GasRow]:
    with open_uow(world.db, readonly=True) as uow:
        return gas_tests_for(uow.conn(), permit, **kw)


def keys(page: IsolationPage) -> list[str]:
    return [r.key for r in page.rows]


@pytest.fixture
def built(world: World) -> Built:
    world.person("dan", ("user", "document_controller"), grant="superuser")
    secret = world.hidden_record()
    b: Built = {}
    b["p1"] = world.approved("general")
    b["p2"] = world.approved("hot_work")
    b["p3"] = world.request("dora", "general", for_record_id=secret)
    world.call("dan", "ApprovePermit", permit=b["p3"])
    b["i1"] = str(world.call("uma", "ApplyIsolation", **POINT).stream_id)
    b["i2"] = str(world.call("rob", "ApplyIsolation", **{**POINT, "energy": "process"}).stream_id)
    b["i3"] = str(world.call("dora", "ApplyIsolation", **POINT, point_record_id=secret).stream_id)
    b["i4"] = str(world.call("uma", "ApplyIsolation", **{**POINT, "energy": "other"}).stream_id)
    world.call("sue", "VerifyIsolation", isolation=b["i1"])
    world.call("uma", "RemoveIsolation", isolation=b["i4"])
    world.call("uma", "LinkIsolation", permit=b["p1"], isolation=b["i1"])
    world.call("dan", "LinkIsolation", permit=b["p3"], isolation=b["i1"])
    for minutes, co in ((-30, "2"), (-20, "30"), (-10, "3")):
        world.call(
            "uma",
            "RecordGasTest",
            permit=b["p2"],
            instrument_text="MX6",
            o2_pct="20.9",
            co_ppm=co,
            taken_at=world.at + timedelta(minutes=minutes),
        )
    world.call(
        "uma", "RecordGasTest", permit=b["p2"], instrument_text="MX6", lel_pct="1", note="Top"
    )
    world.call("dora", "RecordGasTest", permit=b["p3"], instrument_text="MX6", o2_pct="21")
    return b


# --- isolations ---


def test_a_list_is_ordered_by_key_and_hides_the_restricted_point(
    world: World, built: Built
) -> None:
    page = lst(world)
    assert keys(page) == [key(1), key(2), key(4)] and page.total == 3  # the third is hidden
    first = page.rows[0]
    assert (first.id, first.point_text, first.energy, first.state) == (
        built["i1"],
        "Pump P-101 breaker",
        "electrical",
        "Verified",
    )
    assert (first.method, first.lock_number, first.tag_number) == ("Lock and tag", "L-12", "T-12")
    assert (first.applied_by, first.verified_by) == ("user:uma", "user:sue")
    assert first.applied_at == START and first.verified_at == START
    assert first.applied_at.tzinfo is not None
    assert [r.state for r in page.rows] == ["Verified", "Applied", "Removed"]
    assert page.rows[1].verified_by is None and page.rows[1].verified_at is None


def test_each_filter_narrows_and_total_follows(world: World, built: Built) -> None:
    assert keys(lst(world, state="Applied")) == [key(2)]
    assert keys(lst(world, state="Removed")) == [key(4)]
    assert keys(lst(world, energy="process")) == [key(2)]
    assert keys(lst(world, state="Verified", energy="electrical")) == [key(1)]
    assert keys(lst(world, energy="mechanical")) == []
    for kw in ({"state": "Applied"}, {"energy": "electrical"}):
        page = lst(world, **kw)
        assert page.total == len(page.rows)


def test_the_hidden_filter_comes_before_limit_and_before_counting(
    world: World, built: Built
) -> None:
    page = lst(world, limit=2)
    assert keys(page) == [key(1), key(2)] and page.total == 3
    assert keys(lst(world, state="Applied", limit=1)) == [key(2)]  # key 3 is out first
    assert lst(world, state="Applied", limit=1).total == 1
    assert keys(lst(world, limit=3)) == [key(1), key(2), key(4)]


def test_depends_counts_only_the_permits_the_viewer_can_read(world: World, built: Built) -> None:
    rows = {r.key: r for r in lst(world).rows}
    assert (rows[key(1)].depends, rows[key(2)].depends, rows[key(4)].depends) == (1, 0, 0)
    cleared = {r.key: r for r in lst(world, viewer=CLEARED).rows}
    assert cleared[key(1)].depends == 2 and cleared[key(3)].depends == 0


def test_a_detail_has_the_trail_and_the_keys_of_readable_dependents(
    world: World, built: Built
) -> None:
    found = det(world, key(1))
    assert found is not None and found.row.key == key(1) and found.row.depends == 1
    assert found.permits == ["P123-PTW-0001"]  # the hidden third permit is not named
    assert found.point_record_id is None and found.removed_by is None and found.version > 1
    removed = det(world, key(4))
    assert removed is not None and removed.row.state == "Removed"
    assert removed.removed_by == "user:uma" and removed.removed_at == START
    both = det(world, key(1), viewer=CLEARED)
    assert both is not None and both.permits == ["P123-PTW-0001", "P123-PTW-0003"]


def test_a_detail_is_none_for_an_unknown_foreign_or_hidden_number(
    world: World, built: Built
) -> None:
    assert det(world, "P123-ISL-9999") is None
    assert det(world, key(3)) is None  # its point record is restricted
    with open_uow(world.db, readonly=True) as uow:
        assert isolation_detail(uow.conn(), "project:P999", key(1)) is None
    hidden = det(world, key(3), viewer=CLEARED)
    assert hidden is not None and hidden.point_record_id is not None


# --- gas tests ---


def test_gas_tests_come_newest_first_with_their_readings(world: World, built: Built) -> None:
    rows = gas(world, built["p2"])
    assert [r.taken_at for r in rows] == [
        START,
        START - timedelta(minutes=10),
        START - timedelta(minutes=20),
        START - timedelta(minutes=30),
    ]
    assert [r.result for r in rows] == ["pass", "pass", "fail", "pass"]
    assert rows[0].lel_pct == Decimal("1") and rows[0].note == "Top" and rows[0].o2_pct is None
    assert rows[2].co_ppm == Decimal("30") and rows[2].o2_pct == Decimal("20.9")
    assert (rows[0].tester, rows[0].instrument_text) == ("user:uma", "MX6")
    assert all(r.key.startswith("P123-GAS-") and r.taken_at.tzinfo for r in rows)


def test_the_gas_tests_of_a_hidden_permit_are_not_read(world: World, built: Built) -> None:
    assert gas(world, built["p3"]) == []
    assert len(gas(world, built["p3"], viewer=CLEARED)) == 1
    assert gas(world, "01JXXXXXXXXXXXXXXXXXXXXXXX") == []
    assert gas(world, built["p1"]) == []


# --- the hidden default ---


def test_the_viewer_defaults_to_the_lowest_clearance_and_is_keyword_only() -> None:
    for name in ("isolation_list", "isolation_detail", "gas_tests_for"):
        parameter = inspect.signature(getattr(iso_views, name)).parameters["viewer"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is cf.LOWEST, name
    limit = inspect.signature(isolation_list).parameters["limit"]
    assert limit.default == 100 and limit.kind is inspect.Parameter.KEYWORD_ONLY


# --- export ---


def test_isolation_csv_and_jsonl_carry_the_same_rows_as_the_list(
    world: World, built: Built
) -> None:
    rows = lst(world).rows
    parsed = list(csv.reader(io.StringIO(isolation_export_rows(rows, "csv"))))
    assert tuple(parsed[0]) == ISOLATION_EXPORT_COLUMNS
    assert [line[0] for line in parsed[1:]] == [r.key for r in rows]
    first = dict(zip(ISOLATION_EXPORT_COLUMNS, parsed[1], strict=True))
    assert (first["point"], first["energy"], first["state"], first["depends"]) == (
        "Pump P-101 breaker",
        "electrical",
        "Verified",
        "1",
    )
    assert (first["lock"], first["tag"], first["verified_by"]) == ("L-12", "T-12", "user:sue")
    objects = [json.loads(line) for line in isolation_export_rows(rows, "jsonl").splitlines()]
    assert [o["number"] for o in objects] == [r.key for r in rows]
    assert all(set(o) == set(ISOLATION_EXPORT_COLUMNS) for o in objects)
    assert objects[1]["verified_by"] is None and objects[1]["verified"] is None


def test_gas_csv_and_jsonl_carry_the_same_rows(world: World, built: Built) -> None:
    rows = gas(world, built["p2"])
    parsed = list(csv.reader(io.StringIO(gas_export_rows(rows, "csv"))))
    assert tuple(parsed[0]) == GAS_EXPORT_COLUMNS
    assert [line[0] for line in parsed[1:]] == [r.key for r in rows]
    first = dict(zip(GAS_EXPORT_COLUMNS, parsed[1], strict=True))
    assert (first["result"], first["tester"], first["note"], first["o2_pct"]) == (
        "pass",
        "user:uma",
        "Top",
        "",
    )
    objects = [json.loads(line) for line in gas_export_rows(rows, "jsonl").splitlines()]
    assert all(set(o) == set(GAS_EXPORT_COLUMNS) for o in objects)
    assert [o["result"] for o in objects] == ["pass", "pass", "fail", "pass"]
    assert objects[0]["o2_pct"] is None


def test_an_export_of_no_rows_and_a_bad_format() -> None:
    assert isolation_export_rows([], "csv").strip() == ",".join(ISOLATION_EXPORT_COLUMNS)
    assert gas_export_rows([], "csv").strip() == ",".join(GAS_EXPORT_COLUMNS)
    assert isolation_export_rows([], "jsonl") == "" and gas_export_rows([], "jsonl") == ""
    for export in (isolation_export_rows, gas_export_rows):
        with pytest.raises(ValueError, match="csv or jsonl"):
            export([], "xml")


def test_the_row_types_are_frozen_dataclasses() -> None:
    for kind in (IsolationRow, IsolationDetail, IsolationPage, GasRow):
        assert vars(kind)["__dataclass_params__"].frozen
