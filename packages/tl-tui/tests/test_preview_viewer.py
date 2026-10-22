"""open_in_viewer: an argument list, never a shell, the path as one argument (P1-UX2-S4)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tl_tui.preview.viewer import open_in_viewer, viewer_argv


def test_the_default_command_is_the_platforms_opener_and_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_VIEWER_CMD", raising=False)
    argv = viewer_argv(tmp_path / "a.pdf", {})
    assert argv[0] == ("open" if sys.platform == "darwin" else "xdg-open")
    assert argv[1:] == [str(tmp_path / "a.pdf")]


def test_a_name_with_spaces_and_shell_characters_stays_one_argument(tmp_path: Path) -> None:
    name = "my drawing; rm -rf $HOME `x` (1).pdf"
    argv = viewer_argv(tmp_path / name, {})
    assert argv[-1] == str(tmp_path / name) and len(argv) == 2


def test_a_leading_dash_name_is_not_an_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    argv = viewer_argv(Path("-evil.pdf"), {})
    assert argv[-1] == str(tmp_path / "-evil.pdf") and not argv[-1].startswith("-")
    assert viewer_argv(Path("--help"), {})[-1].startswith("/")


def test_tl_viewer_cmd_replaces_the_default_and_is_split_like_a_shell_would(
    tmp_path: Path,
) -> None:
    argv = viewer_argv(tmp_path / "a b.pdf", {"TL_VIEWER_CMD": "/usr/bin/record --to 'a log'"})
    assert argv == ["/usr/bin/record", "--to", "a log", str(tmp_path / "a b.pdf")]


def test_an_empty_override_means_the_default(tmp_path: Path) -> None:
    assert viewer_argv(tmp_path / "a.pdf", {"TL_VIEWER_CMD": "  "})[0] in ("xdg-open", "open")


def test_open_hands_the_argument_list_to_the_launcher(tmp_path: Path) -> None:
    seen: list[Sequence[str]] = []
    open_in_viewer(tmp_path / "a.pdf", seen.append)
    assert len(seen) == 1 and seen[0][-1] == str(tmp_path / "a.pdf")


def test_the_default_launcher_never_uses_a_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[tuple[Any, dict[str, Any]]] = []

    class Spy:
        def __init__(self, argv: Any, **kwargs: Any) -> None:
            started.append((argv, kwargs))

        def wait(self) -> int:
            return 0

    monkeypatch.setenv("TL_VIEWER_CMD", "/bin/true")
    monkeypatch.setattr(subprocess, "Popen", Spy)
    open_in_viewer(tmp_path / "a b.pdf")
    argv, kwargs = started[0]
    assert isinstance(argv, list) and argv == ["/bin/true", str(tmp_path / "a b.pdf")]
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_a_viewer_that_cannot_start_raises_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_VIEWER_CMD", str(tmp_path / "no-such-viewer"))
    with pytest.raises(OSError):
        open_in_viewer(tmp_path / "a.pdf")
