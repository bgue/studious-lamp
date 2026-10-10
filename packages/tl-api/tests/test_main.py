"""The server entry point: argument parsing and the bind rule."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_api import main as server


def test_defaults_bind_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_DB", "TL_TOKENS", "TL_API_HOST", "TL_API_PORT"):
        monkeypatch.delenv(name, raising=False)
    settings = server.parse_args([])
    assert settings.host == "127.0.0.1" and settings.port == 8765
    assert settings.insecure_dev is False


def test_the_environment_and_flags_set_the_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TL_DB", "/x/env.db")
    assert server.parse_args([]).db_path == Path("/x/env.db")
    settings = server.parse_args(["--db", "/y/a.db", "--tokens", "/y/t.json", "--port", "9"])
    assert (settings.db_path, settings.tokens_path, settings.port) == (
        Path("/y/a.db"),
        Path("/y/t.json"),
        9,
    )


def test_a_public_bind_is_refused_without_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = server.main(["--host", "0.0.0.0", "--db", str(tmp_path / "x.db")])
    assert code == 2
    assert "--insecure-dev" in capsys.readouterr().err


def test_a_missing_ledger_is_a_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert server.main(["--db", str(tmp_path / "missing.db")]) == 2
    assert "tl init" in capsys.readouterr().err
