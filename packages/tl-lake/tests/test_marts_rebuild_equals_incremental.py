"""Property: the gold marts and the materials silver of an incremental lake equal a rebuild (P2-I6).

Hypothesis plays a history: IWPs and lots (records standing in for them), readiness evaluations,
movements with their cost codes and IWP ends, sync points, and a schedule snapshot pass in the
middle (two snapshots, published one after the other). The events are appended through the real
ledger and projectors (``LedgerBuilder.raw``): a ``core.Record`` stream carries the module event, so
no module world is needed. After the last syncs, every table of the incremental lake equals the
lake rebuilt from scratch (``sync_lake`` then ``sync_xer``), the silver tables equal the ledger, and
each mart equals its model's SQL run directly over the rebuilt lake's tables.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from builder import SCOPE, LedgerBuilder
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from lakecheck import (
    assert_lake_matches_ledger,
    do_sync,
    do_sync_xer,
    lake_dump,
    lake_table_names,
)
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.errors import ServiceError
from tl_lake import LakeConfig
from tl_lake.duck import open_lake
from tl_lake.gold import GOLD_MODELS, model_sql
from tl_mod_schedule.testing import ScheduleWorld

OPS = st.tuples(
    st.sampled_from(["iwp", "lot", "evaluate", "move", "sync", "schedule", "title"]),
    st.integers(min_value=0, max_value=50),
    st.integers(min_value=0, max_value=50),
)
STATES = ("ok", "blocked", "pending", "n_a")
DAYS = ("2026-10-01", "2026-10-05", "2026-10-12", "2026-10-13", "2026-11-01")
KINDS = ("receive", "receive", "scrap", "transfer")


def checks(i: int, j: int) -> list[dict[str, Any]]:
    return [
        {
            "name": f"check_{k}",
            "version": "1",
            "state": STATES[(i + j * (k + 1)) % 4],
            "detail": "d",
            "resolve_via": [],
            "count_ok": 0,
            "count_total": 1,
        }
        for k in range(1 + j % 3)
    ]


class History:
    def __init__(self, ledger: LedgerBuilder, config: LakeConfig, root: Path) -> None:
        self.ledger, self.config, self.root = ledger, config, root
        self.iwps: list[str] = []
        self.lots: list[str] = []
        self.world: ScheduleWorld | None = None
        self.stage = 0
        self.pending: tuple[str, str] | None = None

    def sync(self) -> None:
        if self.ledger.head():
            do_sync(self.ledger, self.config)

    def schedule(self) -> None:
        if self.world is None:
            self.world = ScheduleWorld(self.ledger.db, self.root / "objects")
            self.world.define()
            self.pending = self.world.two_weeks()
        assert self.pending is not None
        if self.stage < 2:
            self.world.publish(self.pending[self.stage])
            self.stage += 1
        self.sync()
        do_sync_xer(self.ledger, self.config)

    def play(self, n: int, kind: str, i: int, j: int) -> None:
        scope = SCOPE
        if kind == "iwp":
            self.iwps.append(self.ledger.record(f"IWP-{n}", scope=scope))
        elif kind == "lot":
            self.lots.append(self.ledger.record(f"LOT-{n}", scope=scope))
        elif kind == "sync":
            self.sync()
        elif kind == "schedule":
            self.schedule()
        elif kind == "evaluate" and self.iwps:
            self.ledger.evaluate(
                self.iwps[i % len(self.iwps)],
                today=DAYS[j % len(DAYS)],
                ready=j % 2 == 0,
                checks=checks(i, j),
            )
        elif kind == "move" and self.lots:
            more: dict[str, Any] = {}
            if j % 3 == 0 and self.iwps:
                more["iwp_id"] = self.iwps[j % len(self.iwps)]
            if j % 2 == 0:
                more["cost_code_id"] = f"CC-{j % 3}"
            how = KINDS[j % len(KINDS)]
            lot = self.lots[i % len(self.lots)]
            if how == "receive":
                self.ledger.move(lot, how, str(1 + j % 5), to_location_id="L1", **more)
            elif how == "scrap":
                self.ledger.move(lot, how, "1", from_location_id="L1", **more)
            else:
                self.ledger.move(lot, how, "1", from_location_id="L1", to_location_id="L2", **more)
        elif kind == "title" and self.lots:
            self.ledger.update(self.lots[i % len(self.lots)], title=f"title {n}")


def mart_rows(config: LakeConfig, sql: str) -> list[str]:
    with open_lake(config, write=False) as con:
        return sorted(repr(r) for r in con.execute(sql).fetchall())


@settings(
    max_examples=6,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    database=None,
)
@given(ops=st.lists(OPS, min_size=4, max_size=16))
def test_incremental_marts_equal_a_rebuild_and_the_models_run_directly(
    ops: list[tuple[str, int, int]],
) -> None:
    fixtures = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
    with tempfile.TemporaryDirectory() as tmp, use_provider(DirectorySchemaProvider(fixtures)):
        root = Path(tmp)
        ledger = LedgerBuilder.create(root / "tl.db")
        incremental = LakeConfig.at(root / "incremental")
        history = History(ledger, incremental, root)
        for n, (kind, i, j) in enumerate(ops):
            try:
                history.play(n, kind, i, j)
            except (ServiceError, ConcurrencyError, ValueError):
                continue  # a command the current state refuses: the history skips it
        if ledger.head() == 0:
            return
        do_sync(ledger, incremental)
        do_sync_xer(ledger, incremental)
        rebuilt = LakeConfig.at(root / "rebuilt")
        do_sync(ledger, rebuilt)
        do_sync_xer(ledger, rebuilt)

        names = lake_table_names(incremental)
        assert names == lake_table_names(rebuilt)
        for table in names:
            if table.startswith("_tl_"):
                continue  # the sync bookkeeping names snapshots; it differs by design
            assert lake_dump(incremental, table) == lake_dump(rebuilt, table), table
        assert_lake_matches_ledger(ledger, incremental, rebuilt)
        for model in GOLD_MODELS:
            if model.name not in names:
                continue
            direct = mart_rows(rebuilt, f"SELECT * FROM ({model_sql(model.name)})")
            assert mart_rows(rebuilt, f"SELECT * FROM {model.name}") == direct, model.name
            assert mart_rows(incremental, f"SELECT * FROM {model.name}") == direct, model.name
