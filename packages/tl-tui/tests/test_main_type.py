"""``--type`` / ``TL_TYPE`` choose the record type of the grid (P0-I8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import create_schema
from tl_tui.main import DEFAULT_TYPE, make_app


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    monkeypatch.delenv("TL_TYPE", raising=False)
    monkeypatch.delenv("TL_REMOTE", raising=False)
    return path


def test_the_grid_shows_core_records_by_default(db: Path) -> None:
    assert make_app(db=db).record_type == DEFAULT_TYPE == "core.Record"


def test_an_option_names_an_extension_type(db: Path) -> None:
    assert make_app(db=db, record_type="co.acme.LiftPlan").record_type == "co.acme.LiftPlan"


def test_the_environment_names_it_when_no_option_does(
    db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_TYPE", "co.acme.SafetyObservation")
    assert make_app(db=db).record_type == "co.acme.SafetyObservation"
    assert make_app(db=db, record_type="co.acme.LiftPlan").record_type == "co.acme.LiftPlan"
