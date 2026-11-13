"""Marts and the materials silver hold nothing of a hidden record (P2-I6-S1, ADR-0016, SR-X1).

Walking test. Lots, IWPs and requisitions are never confidential in the installed modules, so the
test declares one of its own, as a module would: every ``core.Record`` has a class in the ledger
table ``lake_test_class``, ``internal`` or ``restricted`` (a record with no row is hidden). The
rows of silver and of every mart must name no hidden record, in a cell or in a count; a record that
is declassified comes back at the next sync and one that is classified leaves; the lake after it
all equals one rebuilt from scratch.

The bronze ``events`` keep what the lake always keeps: an event of a stream that was readable when
copied stays until the next rebuild (ADR-0016), so the mart built from bronze (the readiness
history) follows a reclassification at a rebuild, and the tests say so.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from builder import LedgerBuilder
from lakecheck import do_sync, lake_dump, lake_table_names
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.modules import ConfidentialSource, confidential_sources
from tl_lake import LakeConfig
from tl_lake.duck import open_lake
from tl_lake.gold import GOLD_MODELS, model_sql

CLASS_TABLE = "lake_test_class"
MARTS = tuple(m.name for m in GOLD_MODELS)
SILVER = ("cur_core_record", "cur_materials_movement", "cur_materials_stock")


@pytest.fixture(autouse=True)
def test_family(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    real = confidential_sources
    mine = ConfidentialSource(frozenset({"core.Record"}), CLASS_TABLE, "id", "klass")

    def sources() -> list[ConfidentialSource]:
        return [*real(), mine]

    monkeypatch.setattr("tl_core.confidentiality.confidential_sources", sources)
    monkeypatch.setattr("tl_lake.sync.confidential_sources", sources)
    yield


def classify(ledger: LedgerBuilder, record_id: str, klass: str) -> None:
    """Set the class of a record and write an event on it, so the next sync sees a change."""
    engine = ledger.engine()
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {CLASS_TABLE} WHERE id = :i"), {"i": record_id})
            conn.execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, klass) VALUES (:i, :k)"),
                {"i": record_id, "k": klass},
            )
    finally:
        engine.dispose()
    with confidentiality.system_view():  # the command layer hides what the viewer may not read
        ledger.update(record_id, title=f"{klass} {ledger.versions[record_id]}")


def check(name: str, state: str, via: list[str]) -> dict[str, Any]:
    return {
        "name": name, "version": "1", "state": state, "detail": "d", "resolve_via": via,
        "count_ok": 0, "count_total": 1,
    }  # fmt: skip


class World:
    """Two IWPs, two lots and two requisition ids, one of each hidden; movements around them."""

    def __init__(self, ledger: LedgerBuilder) -> None:
        engine = ledger.engine()
        try:
            with engine.begin() as conn:
                conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, klass TEXT)"))
        finally:
            engine.dispose()
        self.ledger = ledger
        names = ("iwp_ok", "iwp_hid", "lot_ok", "lot_hid", "req_ok", "req_hid")
        self.ids = {n: ledger.record(n.upper()) for n in names}
        for n, i in self.ids.items():
            classify(ledger, i, "restricted" if n.endswith("hid") else "internal")
        self.hidden = {self.ids[n] for n in names if n.endswith("hid")}
        i = self.ids
        ledger.evaluate(
            i["iwp_ok"], today="2026-11-02", ready=False,
            checks=[check("a", "blocked", [i["req_hid"], i["lot_hid"]]), check("b", "ok", [])],
        )  # fmt: skip
        ledger.evaluate(
            i["iwp_hid"], today="2026-11-02", ready=False, checks=[check("c", "blocked", [])]
        )
        move = ledger.move
        move(i["lot_ok"], "receive", "10", to_location_id="L1")  # visible, no ends at all
        move(i["lot_ok"], "scrap", "1", from_location_id="L1", iwp_id=i["iwp_ok"])  # visible
        move(i["lot_ok"], "receive", "2", to_location_id="L1", requisition_id=i["req_ok"])
        self.visible = ledger.head()
        move(i["lot_hid"], "receive", "9", to_location_id="L1")  # a hidden lot
        move(i["lot_ok"], "receive", "3", to_location_id="L1", requisition_id=i["req_hid"])
        move(i["lot_ok"], "receive", "4", to_location_id="L1", iwp_id=i["iwp_hid"])
        self.head = ledger.head()


def table_text(config: LakeConfig, tables: tuple[str, ...]) -> str:
    out: list[str] = []
    with open_lake(config, write=False) as con:
        for name in tables:
            out += [
                " ".join(map(str, r)) for r in con.execute(f'SELECT * FROM "{name}"').fetchall()
            ]
    return "\n".join(out)


def count(config: LakeConfig, sql: str) -> Any:
    with open_lake(config, write=False) as con:
        return con.execute(sql).fetchone()[0]  # type: ignore[index]


def movement_seqs(config: LakeConfig) -> list[int]:
    with open_lake(config, write=False) as con:
        rows = con.execute("SELECT seq FROM cur_materials_movement ORDER BY seq").fetchall()
        return [r[0] for r in rows]


def marts_in(config: LakeConfig) -> tuple[str, ...]:
    present = set(lake_table_names(config))
    return tuple(m for m in MARTS if m in present)


def rebuilt(ledger: LedgerBuilder, root: Path, name: str) -> LakeConfig:
    config = LakeConfig.at(root / name)
    do_sync(ledger, config)
    return config


def assert_nothing_of(config: LakeConfig, hidden: set[str], marts: tuple[str, ...]) -> None:
    text_of = table_text(config, (*SILVER, *marts))
    for record_id in sorted(hidden):
        assert record_id not in text_of, record_id


def assert_marts_are_the_models_over_the_lake(config: LakeConfig) -> None:
    """Each mart is its model run over the lake's own tables: a function of silver and bronze."""
    with open_lake(config, write=False) as con:
        for name in marts_in(config):
            direct = sorted(map(repr, con.execute(f"SELECT * FROM ({model_sql(name)})").fetchall()))
            held = sorted(map(repr, con.execute(f"SELECT * FROM {name}").fetchall()))
            assert held == direct, name


def test_a_hidden_record_is_in_no_silver_row_no_mart_cell_and_no_count(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    world = World(ledger)
    do_sync(ledger, lake)
    assert_nothing_of(lake, world.hidden, marts_in(lake))
    assert marts_in(lake) == MARTS[:2]
    # silver: the three visible movements only; the lot that is hidden has no stock row; a
    # movement whose lot, IWP or requisition is hidden is gone, a NULL end is kept
    assert len(movement_seqs(lake)) == 3 and max(movement_seqs(lake)) <= world.visible
    ids = world.ids
    assert count(lake, "SELECT count(*) FROM cur_materials_stock") == 1
    assert (
        count(lake, f"SELECT count(*) FROM cur_materials_stock WHERE lot_id = '{ids['lot_ok']}'")
        == 1
    )
    # the marts count what silver and bronze hold, nothing more
    assert count(lake, "SELECT COALESCE(sum(movements), 0) FROM mart_materials") in (0, 3)
    assert count(lake, "SELECT COALESCE(sum(lots), 0) FROM mart_materials") in (0, 2)
    assert count(lake, "SELECT count(DISTINCT iwp_id) FROM mart_iwp_readiness_history") in (0, 1)
    assert count(lake, "SELECT COALESCE(sum(checks_total), 0) FROM mart_iwp_readiness_history") in (
        0,
        2,
    )
    assert_marts_are_the_models_over_the_lake(lake)


def test_the_events_of_a_hidden_iwp_are_redacted_rows_in_bronze(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    world = World(ledger)
    do_sync(ledger, lake)
    iwp = world.ids["iwp_hid"]
    assert count(lake, f"SELECT count(*) FROM events WHERE stream_id = '{iwp}'") == 0
    assert count(lake, "SELECT count(*) FROM events WHERE event_type = 'Internal.Redacted'") > 0


def test_declassify_brings_rows_back_reclassify_removes_them_and_a_rebuild_equals(
    ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Path
) -> None:
    world = World(ledger)
    ids = world.ids
    do_sync(ledger, lake)
    before = movement_seqs(lake)

    for name in ("lot_hid", "iwp_hid", "req_hid"):
        classify(ledger, ids[name], "internal")
    do_sync(ledger, lake)
    assert len(movement_seqs(lake)) == 6  # the rows of the declassified records appear
    assert count(lake, "SELECT count(*) FROM cur_materials_stock") == 2  # both lots at L1
    assert set(before) < set(movement_seqs(lake))
    assert_marts_are_the_models_over_the_lake(lake)
    again = rebuilt(ledger, tmp_path, "fresh1")
    for table in (*SILVER, "mart_materials"):
        assert lake_dump(lake, table) == lake_dump(again, table), table

    for name in ("lot_hid", "iwp_hid", "req_hid"):
        classify(ledger, ids[name], "restricted")
    do_sync(ledger, lake)
    assert movement_seqs(lake) == before  # they leave again
    assert (
        count(lake, f"SELECT count(*) FROM cur_materials_stock WHERE lot_id = '{ids['lot_hid']}'")
        == 0
    )
    assert_nothing_of(lake, world.hidden, ("mart_materials",))
    assert_marts_are_the_models_over_the_lake(lake)
    # the readiness history is built from bronze: an event copied while readable stays there until
    # a rebuild (ADR-0016), so only the rebuilt lake is exact about it
    again = rebuilt(ledger, tmp_path, "fresh2")
    assert_nothing_of(again, world.hidden, marts_in(again))
    for table in (*SILVER, "mart_materials"):
        assert lake_dump(lake, table) == lake_dump(again, table), table
