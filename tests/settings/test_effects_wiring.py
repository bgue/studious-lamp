"""`tl projections rebuild` and the server start carry out settings effects (P0-I8 D6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import open_uow
from tl_api import main as server
from tl_api.tokens import add_token
from tl_cli.main import app
from tl_core import settings
from tl_core.settings.types import SettingEffect
from tl_core.settings.views import get_view
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    db = tmp_path / "tl.db"
    assert runner.invoke(app, ["--db", str(db), "init"]).exit_code == 0
    for key in ("t.restart", "t.rebuild"):
        with open_uow(db) as uow:
            settings.set_setting(
                uow, key=key, layer="company", value=3, actor="user:dev", source="test"
            )
    return db


def owed(db: Path, key: str) -> SettingEffect | None:
    with open_uow(db) as uow:
        return get_view(uow.conn(), key).effective.pending_effect


def rebuild(db: Path, *args: str) -> None:
    result = runner.invoke(app, ["--db", str(db), "projections", "rebuild", *args])
    assert result.exit_code == 0, result.output


def test_both_keys_owe_their_effect_after_a_change(ledger: Path) -> None:
    assert owed(ledger, "t.restart") == "restart"
    assert owed(ledger, "t.rebuild") == "rebuild"


def test_a_full_rebuild_carries_out_rebuild_and_leaves_restart_owed(ledger: Path) -> None:
    rebuild(ledger)
    assert owed(ledger, "t.rebuild") is None
    assert owed(ledger, "t.restart") == "restart"


def test_a_partial_rebuild_carries_out_nothing(ledger: Path) -> None:
    rebuild(ledger, "--only", "settings")
    assert owed(ledger, "t.rebuild") == "rebuild"


def test_a_change_after_the_rebuild_is_owed_again(ledger: Path) -> None:
    rebuild(ledger)
    with open_uow(ledger) as uow:
        settings.set_setting(
            uow, key="t.rebuild", layer="company", value=4, actor="user:dev", source="test"
        )
    assert owed(ledger, "t.rebuild") == "rebuild"


def test_the_server_start_carries_out_restart_and_leaves_rebuild_owed(
    ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    started: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(a))
    tokens = tmp_path / "tokens.json"
    add_token(tokens, "user:dev")
    code = server.main(["--db", str(ledger), "--tokens", str(tokens)])
    assert code == 0 and len(started) == 1
    assert owed(ledger, "t.restart") is None
    assert owed(ledger, "t.rebuild") == "rebuild"
