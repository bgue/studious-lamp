"""``render_screen``: a headless TUI screen as SVG and text, on a copy of the dev ledger."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_mcp.dev import tool_render_screen
from tl_mcp.dev.guard import resolve_target
from tl_mcp.dev.tool_render_screen import _is_key_name

PREFIX = "tl-render-"


@pytest.fixture
def env(tmp_path: Path) -> DevHarness:
    """A dev server whose repository is a small copy tree, so snapshots go to tmp_path."""
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# test repository\n", encoding="utf-8")
    (repo / "justfile").write_text("default:\n    @true\n", encoding="utf-8")
    harness = DevHarness.build(tmp_path, repo_root=repo)
    harness.create_record("V-1", "Valve one", scope="project:P123")
    harness.create_record("V-2", "Valve two", scope="project:P123")
    return harness


def _count_records(db: Path) -> int:
    con = sqlite3.connect(db)
    try:
        return int(con.execute("SELECT count(*) FROM cur_core_record").fetchone()[0])
    finally:
        con.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(env: DevHarness, **arguments: Any) -> dict[str, Any]:
    out: dict[str, Any] = env.structured("render_screen", **arguments)
    return out


def _temp_render_dirs() -> list[Path]:
    return [p for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith(PREFIX)]


def test_the_default_screen_is_an_svg_with_the_records_as_text(env: DevHarness) -> None:
    out = _render(env)
    assert out["svg"].startswith("<svg")
    assert out["svg_truncated"] is False
    assert "V-1" in out["text"] and "Valve one" in out["text"]
    assert out["file"] == "dev/data/snapshots/screen.svg"
    assert out["width"] == 120 and out["height"] == 40 and out["keys"] == []
    saved = env.ctx.repo_root / out["file"]
    assert saved.read_text(encoding="utf-8") == out["svg"]


def test_enter_opens_the_record_and_f1_shows_the_key_map(env: DevHarness) -> None:
    grid = _render(env)
    opened = _render(env, keys=["enter"])
    assert "Details" in opened["text"] and "V-1" in opened["text"]
    assert opened["text"] != grid["text"]
    key_map = _render(env, keys=["f1"])
    assert "Show this key map" in key_map["text"]
    assert key_map["text"] != grid["text"]


def test_an_unknown_key_name_is_a_tool_error_not_a_hang(env: DevHarness) -> None:
    with pytest.raises(ToolError, match="unknown key name 'nokey'"):
        env.call("render_screen", keys=["nokey"])
    assert not (env.ctx.snapshots_dir / "screen.svg").exists()


def test_the_size_sets_the_text_rows(env: DevHarness) -> None:
    out = _render(env, width=80, height=24)
    rows = out["text"].split("\n")
    assert out["width"] == 80 and out["height"] == 24
    assert len(rows) <= 24
    assert max(len(row) for row in rows) <= 80


def test_keys_never_write_to_the_dev_ledger(env: DevHarness) -> None:
    records_before = _count_records(env.db)
    bytes_before = _sha256(env.db)
    out = _render(env, keys=["n", "a", "b", "c", "ctrl+s"])
    assert "abc" in out["text"].lower()  # the form saved, but on the copy
    assert _count_records(env.db) == records_before
    assert _sha256(env.db) == bytes_before


def test_another_project_renders_an_empty_grid(env: DevHarness) -> None:
    out = _render(env, project="P999")
    assert out["svg"].startswith("<svg")
    assert "V-1" not in out["text"]


def test_a_postgres_target_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# test repository\n", encoding="utf-8")
    (repo / "justfile").write_text("default:\n    @true\n", encoding="utf-8")
    target = resolve_target("postgresql://postgres:x@localhost/tl_test", repo_root=repo)
    env = DevHarness.build(tmp_path, repo_root=repo, target=target)
    with pytest.raises(ToolError, match="refused"):
        env.call("render_screen")


def test_a_missing_database_file_is_a_tool_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# test repository\n", encoding="utf-8")
    (repo / "justfile").write_text("default:\n    @true\n", encoding="utf-8")
    env = DevHarness.build(tmp_path, repo_root=repo, create=False)
    with pytest.raises(ToolError, match="does not exist"):
        env.call("render_screen")


@pytest.mark.parametrize(
    "arguments",
    [
        {"keys": [f"k{i}" for i in range(21)]},
        {"keys": ["a b"]},
        {"width": 500},
        {"name": "../x"},
    ],
    ids=["too-many-keys", "key-with-space", "width-too-large", "name-with-dots"],
)
def test_schema_refusals_write_no_file(env: DevHarness, arguments: dict[str, Any]) -> None:
    with pytest.raises(ToolError):
        env.call("render_screen", **arguments)
    snapshots = env.ctx.snapshots_dir
    assert not snapshots.exists() or not any(snapshots.iterdir())


def test_two_names_leave_two_files_and_the_same_name_replaces(env: DevHarness) -> None:
    first = _render(env, name="first")
    second = _render(env, name="second")
    assert first["file"] == "dev/data/snapshots/first.svg"
    assert second["file"] == "dev/data/snapshots/second.svg"
    assert sorted(p.name for p in env.ctx.snapshots_dir.iterdir()) == ["first.svg", "second.svg"]
    replaced = _render(env, name="first", keys=["enter"])
    assert sorted(p.name for p in env.ctx.snapshots_dir.iterdir()) == ["first.svg", "second.svg"]
    saved = env.ctx.repo_root / replaced["file"]
    assert saved.read_text(encoding="utf-8") == replaced["svg"]
    assert replaced["svg"] != first["svg"]


def test_no_temporary_directory_is_left_behind(env: DevHarness) -> None:
    before = len(_temp_render_dirs())
    _render(env, keys=["enter"])
    assert len(_temp_render_dirs()) == before


def test_a_screen_that_does_not_settle_is_a_tool_error(
    env: DevHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stand-in run that never returns: a real app cancelled mid-startup leaves Textual's
    # internal coroutines unawaited (a RuntimeWarning later, in an unrelated test).
    async def never_settles(*args: object) -> tuple[str, str]:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    monkeypatch.setattr(tool_render_screen, "_screen", never_settles)
    monkeypatch.setattr(tool_render_screen, "SETTLE_TIMEOUT_S", 0.05)
    before = len(_temp_render_dirs())
    with pytest.raises(ToolError, match="did not settle"):
        env.call("render_screen")
    assert len(_temp_render_dirs()) == before


@pytest.mark.parametrize(
    "key",
    [
        "enter",
        "down",
        "f2",
        "ctrl+p",
        "slash",
        "shift+down",
        "alt+left",
        "left_square_bracket",
        "F",
    ],
)
def test_textual_key_names_are_accepted(key: str) -> None:
    assert _is_key_name(key)


@pytest.mark.parametrize("key", ["nokey", "ctrl+nokey", "ctrl+", "ctrl"])
def test_names_textual_cannot_map_are_refused(key: str) -> None:
    assert not _is_key_name(key)
