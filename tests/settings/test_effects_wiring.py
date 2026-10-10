"""`tl projections rebuild` and the server start carry out settings effects (P0-I8 D6)."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import Connection
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


def serve_args(ledger: Path, tmp_path: Path, port: int) -> list[str]:
    tokens = tmp_path / "tokens.json"
    add_token(tokens, "user:dev")
    return ["--db", str(ledger), "--tokens", str(tokens), "--port", str(port)]


def test_the_server_start_carries_out_restart_once_it_listens(ledger: Path, tmp_path: Path) -> None:
    from tl_api.app import create_app
    from tl_api.backend import open_sqlite_backend
    from tl_api.settings import ApiSettings

    port = free_port()
    backend = open_sqlite_backend(ledger)
    settings = ApiSettings(db_path=ledger, tokens_path=tmp_path / "tokens.json", port=port)
    add_token(settings.tokens_path, "user:dev")
    app = create_app(backend, settings=settings)
    listening = server.started_server(app, settings, lambda: server.mark_server_started(backend))
    thread = threading.Thread(target=listening.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while owed(ledger, "t.restart") is not None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert owed(ledger, "t.restart") is None
        assert owed(ledger, "t.rebuild") == "rebuild"
    finally:
        listening.should_exit = True
        thread.join(timeout=20)
        backend.close()


def test_a_port_that_cannot_be_bound_leaves_restart_pending(ledger: Path, tmp_path: Path) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = int(busy.getsockname()[1])
        with pytest.raises(SystemExit):
            server.main(serve_args(ledger, tmp_path, port))
    assert owed(ledger, "t.restart") == "restart"


def test_an_app_that_cannot_be_built_leaves_restart_pending(
    ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tl_api.app

    def broken(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("cannot build the app")

    monkeypatch.setattr(tl_api.app, "create_app", broken)
    with pytest.raises(RuntimeError, match="cannot build"):
        server.main(serve_args(ledger, tmp_path, free_port()))
    assert owed(ledger, "t.restart") == "restart"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_the_rebuild_marks_up_to_the_last_event_it_replayed(ledger: Path) -> None:
    """A change written after the replay (before the mark could be written) stays owed."""
    from tl_adapters.sqlite.uow import rebuild_projections
    from tl_core.settings.effects import mark_applied

    seen: list[int] = []

    def mark(conn: Connection, last_seq: int) -> None:
        seen.append(last_seq)
        mark_applied(conn, ["rebuild", "reindex"], applied_by="rebuild", head=last_seq)

    replayed = rebuild_projections(ledger, after_replay=mark)
    assert seen == [replayed] and owed(ledger, "t.rebuild") is None
    with open_uow(ledger) as uow:  # arrives after the replay, as if during the gap
        settings.set_setting(
            uow, key="t.rebuild", layer="company", value=9, actor="user:dev", source="test"
        )
    assert owed(ledger, "t.rebuild") == "rebuild"


def test_mark_applied_covers_only_the_head_it_is_given(ledger: Path) -> None:
    from tl_core.settings.effects import mark_applied

    with open_uow(ledger, readonly=True) as uow:
        head = uow.ledger.head_seq()
    with open_uow(ledger) as uow:
        settings.set_setting(
            uow, key="t.rebuild", layer="company", value=9, actor="user:dev", source="test"
        )
        mark_applied(uow.conn(), ["rebuild"], applied_by="rebuild", head=head)
    assert owed(ledger, "t.rebuild") == "rebuild"  # the change is newer than `head`


def test_a_failing_hook_rolls_the_whole_rebuild_back(ledger: Path) -> None:
    from tl_adapters.sqlite.uow import rebuild_projections

    def fail(conn: Connection, last_seq: int) -> None:
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        rebuild_projections(ledger, after_replay=fail)
    assert owed(ledger, "t.rebuild") == "rebuild"
    with open_uow(ledger, readonly=True) as uow:
        view = get_view(uow.conn(), "t.rebuild")
    assert view.effective.value == 3  # the setting rows are still there
