"""Open a file in the system viewer (P1-UX2-S4).

The command is an argument list, never a shell line: ``xdg-open`` (Linux), ``open`` (macOS) or
``os.startfile`` (Windows). ``TL_VIEWER_CMD`` (split with ``shlex``) replaces the default; the demo
and the tests point it at a script that records the path. The viewer is started in its own session
so closing the TUI does not close it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

Launcher = Callable[[Sequence[str]], None]


def viewer_argv(path: Path, env: Mapping[str, str] | None = None) -> list[str]:
    """The command that opens ``path``: the viewer words, then the absolute path as one argument."""
    source = os.environ if env is None else env
    target = os.path.abspath(path)
    if target.startswith("-"):  # never an option, even if the path were not absolute
        target = "./" + target
    override = source.get("TL_VIEWER_CMD", "").strip()
    if override:
        return [*shlex.split(override), target]
    if sys.platform == "darwin":
        return ["open", target]
    return ["xdg-open", target]


def _launch(argv: Sequence[str]) -> None:
    if sys.platform == "win32" and not os.environ.get("TL_VIEWER_CMD", "").strip():
        os.startfile(argv[-1])  # type: ignore[attr-defined,unused-ignore]  # noqa: S606
        return
    child = subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        start_new_session=True,
    )
    threading.Thread(target=child.wait, daemon=True).start()  # reap it when it ends


def open_in_viewer(path: Path, launcher: Launcher | None = None) -> None:
    """Open ``path`` in the viewer; ``OSError`` if the viewer cannot be started."""
    (launcher or _launch)(viewer_argv(path))
