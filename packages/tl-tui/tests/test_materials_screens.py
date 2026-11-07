"""Stock and Movement log screens at 80 and 170 columns (T06f, T06g)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06f  # noqa: E402
import acc_t06g  # noqa: E402
from acc_runner import ledger_copy, point_at_seed  # noqa: E402
from tl_adapters.sqlite.factory import SqliteUowFactory  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402

SIZES = acc_t06f.SIZES
IDS = [f"{w}x{h}" for w, h in SIZES]


@pytest.fixture
def db(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    point_at_seed(acc_t06f, tmp_path_factory, monkeypatch)
    point_at_seed(acc_t06g, tmp_path_factory, monkeypatch)
    return ledger_copy(acc_t06f, tmp_path)


@pytest.fixture
def client(db: Path) -> EmbeddedClient:
    return EmbeddedClient(SqliteUowFactory(db), actor=acc_t06f.ALICE)


@pytest.mark.parametrize("size", SIZES, ids=IDS)
def test_stock_screen_walk(client: EmbeddedClient, size: tuple[int, int]) -> None:
    rows = client.list_materials_stock(acc_t06f.PROJECT, limit=1000)
    assert rows
    acc_t06f.stock_at(size, client, rows)


@pytest.mark.parametrize("size", SIZES, ids=IDS)
def test_movement_log_screen_walk(client: EmbeddedClient, size: tuple[int, int]) -> None:
    acc_t06f.movements_at(size, client)


@pytest.mark.parametrize("size", SIZES, ids=IDS)
def test_empty_stock_screen(size: tuple[int, int]) -> None:
    acc_t06f.empty_stock_at(size)


def test_movement_signs_per_kind() -> None:
    acc_t06g.check_signs()


def test_movement_for_cell() -> None:
    acc_t06g.check_for_cell()


def test_movement_columns_drop_order() -> None:
    acc_t06g.check_columns()


def test_lot_panel_reservations() -> None:
    acc_t06g.check_lot_reservations()


@pytest.mark.parametrize("size", SIZES, ids=IDS)
def test_work_package_on_lot_panel_and_movement_log(db: Path, size: tuple[int, int]) -> None:
    base = EmbeddedClient(SqliteUowFactory(db), actor=acc_t06g.ALICE)
    rows = base.list_materials_stock(acc_t06g.PROJECT, limit=1000)
    assert rows
    client = acc_t06g.WithWorkPackage(SqliteUowFactory(db), actor=acc_t06g.ALICE, first=rows[0])
    acc_t06g.stock_at(size, client)
    acc_t06g.movements_at(size, client)
