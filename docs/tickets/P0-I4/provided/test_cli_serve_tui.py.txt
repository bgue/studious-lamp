"""`tl serve` and `tl tui` (P0-I4-T61). Provided; do not edit.

Both commands are thin: they hand the root options to ``tl_api.main.main`` and
``tl_tui.main.run``. The tests replace those two functions, so no server starts and no terminal
opens; the end-to-end run is the P0-I4 demo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tl_cli.main import app
from typer.testing import CliRunner, Result

runner = CliRunner()


def invoke(*args: str, env: dict[str, str] | None = None) -> Result:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_REMOTE", "TL_TOKEN", "TL_PROJECT", "TL_TOKENS", "TL_DB"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def api_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_main(argv: Any = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("tl_api.main.main", fake_main)
    return calls


@pytest.fixture
def tui_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)
        if kwargs.get("remote") == "ftp://nope":
            raise ValueError("--remote must be an http(s) URL, got 'ftp://nope'")

    monkeypatch.setattr("tl_tui.main.run", fake_run)
    return calls


def test_both_commands_are_listed_in_the_help() -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    assert "serve" in result.stdout and "tui" in result.stdout


def test_serve_passes_the_root_db_and_the_defaults_to_the_api(
    api_calls: list[list[str]], tmp_path: Path
) -> None:
    db = tmp_path / "x.db"
    result = invoke("--db", str(db), "serve")
    assert result.exit_code == 0, result.output
    assert api_calls == [
        [
            "--db",
            str(db),
            "--tokens",
            "dev/data/tokens.json",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ]
    ]


def test_serve_options_reach_the_api_and_insecure_dev_is_a_flag(
    api_calls: list[list[str]], tmp_path: Path
) -> None:
    tokens = tmp_path / "t.json"
    result = invoke(
        "--db",
        str(tmp_path / "x.db"),
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "9000",
        "--tokens",
        str(tokens),
        "--insecure-dev",
    )
    assert result.exit_code == 0, result.output
    argv = api_calls[0]
    assert argv[argv.index("--host") + 1] == "0.0.0.0"
    assert argv[argv.index("--port") + 1] == "9000"
    assert argv[argv.index("--tokens") + 1] == str(tokens)
    assert argv[-1] == "--insecure-dev"


def test_serve_exits_with_the_servers_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("tl_api.main.main", lambda argv=None: 2)
    result = invoke("--db", str(tmp_path / "x.db"), "serve")
    assert result.exit_code == 2


def test_tui_is_embedded_by_default_on_the_root_db(
    tui_calls: list[dict[str, Any]], tmp_path: Path
) -> None:
    db = tmp_path / "x.db"
    result = invoke("--db", str(db), "tui")
    assert result.exit_code == 0, result.output
    assert tui_calls == [{"remote": None, "token": None, "db": db, "project": None, "actor": None}]


def test_tui_remote_options_reach_run(tui_calls: list[dict[str, Any]], tmp_path: Path) -> None:
    result = invoke(
        "--db",
        str(tmp_path / "x.db"),
        "tui",
        "--remote",
        "http://127.0.0.1:8765",
        "--token",
        "tok",
        "--project",
        "P9",
        "--actor",
        "user:me",
    )
    assert result.exit_code == 0, result.output
    call = tui_calls[0]
    assert call["remote"] == "http://127.0.0.1:8765" and call["token"] == "tok"
    assert call["project"] == "P9" and call["actor"] == "user:me"


def test_tui_reads_the_remote_and_the_token_from_the_environment(
    tui_calls: list[dict[str, Any]], tmp_path: Path
) -> None:
    env = {"TL_REMOTE": "http://127.0.0.1:1", "TL_TOKEN": "from-env"}
    result = invoke("--db", str(tmp_path / "x.db"), "tui", env=env)
    assert result.exit_code == 0, result.output
    assert tui_calls[0]["remote"] == "http://127.0.0.1:1" and tui_calls[0]["token"] == "from-env"


def test_tui_reports_a_bad_option_on_stderr_and_exits_2_without_the_token(
    tui_calls: list[dict[str, Any]], tmp_path: Path
) -> None:
    result = invoke(
        "--db", str(tmp_path / "x.db"), "tui", "--remote", "ftp://nope", "--token", "s3cret"
    )
    assert result.exit_code == 2
    assert "error: --remote must be an http(s) URL" in result.stderr
    assert "s3cret" not in result.stdout and "s3cret" not in result.stderr
