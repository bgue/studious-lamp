"""Draw page 1 of a PDF as a PNG, bounded and off the UI thread (P1-UX2-S4).

``render_first_page`` is the parent. It refuses a file over ``MAX_BYTES`` or without the ``%PDF-``
header without starting anything, answers from the cache by content hash when it can, and
otherwise runs ``python -I -m tl_tui.preview._worker`` as a child (argument list, stripped
environment, no stdin, own process group) that it kills at the timeout. The PDF is never opened in
this process.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tl_tui.preview import cache

MAX_BYTES = 50 * 1024 * 1024
HEADER = b"%PDF-"
#: The child's command. A test points it at a script that misbehaves.
WORKER_COMMAND: tuple[str, ...] = (sys.executable, "-I", "-m", "tl_tui.preview._worker")
_MAX_ANSWER = 4096  # bytes of the child's answer that are read

State = Literal["ok", "not_pdf", "too_big", "timeout", "error"]
_STATES = ("not_pdf", "too_big", "timeout", "error")


@dataclass
class PreviewResult:
    state: State
    pages: int | None = None
    png: Path | None = None


def _header_ok(path: Path) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return False
    with os.fdopen(fd, "rb") as handle:
        return handle.read(len(HEADER)) == HEADER


def _child_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if sys.platform == "win32":  # pragma: no cover  (the interpreter needs this one to start)
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


def _kill(child: subprocess.Popen[bytes]) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(child.pid, signal.SIGKILL)
        else:  # pragma: no cover
            child.kill()
    except (ProcessLookupError, PermissionError):
        child.kill()
    child.wait()


def render_first_page(
    path: Path,
    sha256: str,
    *,
    timeout_s: float = 8.0,
    root: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PreviewResult:
    """Page 1 of ``path`` (whose content hash is ``sha256``) as a cached PNG.

    ``state`` is ``ok`` (``png`` and, when known, ``pages`` are set), ``not_pdf``, ``too_big`` (over
    ``MAX_BYTES``), ``timeout`` (the child was killed) or ``error`` (anything else; never a text).
    ``cancelled`` is polled while the child runs; when it turns true the child is killed and the
    answer is ``error``.
    """
    directory = cache.cache_dir() if root is None else root
    if not cache.valid_hash(sha256):
        return PreviewResult("error")
    hit = cache.lookup(directory, sha256)
    if hit is not None:
        return PreviewResult("ok", cache.read_pages(hit), hit)
    try:
        size = os.lstat(path).st_size
    except OSError:
        return PreviewResult("error")
    if size > MAX_BYTES:
        return PreviewResult("too_big")
    if not _header_ok(path):
        return PreviewResult("not_pdf")
    try:
        cache.ensure_dir(directory)
        child = subprocess.Popen(
            [*WORKER_COMMAND, str(path), sha256, str(directory)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_child_env(),
            shell=False,
            start_new_session=True,
        )
    except (OSError, ValueError):
        return PreviewResult("error")
    outcome: dict[str, bytes] = {}

    def collect() -> None:
        assert child.stdout is not None
        outcome["answer"] = child.stdout.read(_MAX_ANSWER)

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_s
    while child.poll() is None:
        if cancelled is not None and cancelled():
            _kill(child)
            reader.join(1)
            return PreviewResult("error")
        if time.monotonic() >= deadline:
            _kill(child)
            reader.join(1)
            return PreviewResult("timeout")
        time.sleep(0.02)
    reader.join(1)
    child.wait()
    return _result(child.returncode, outcome.get("answer", b""), directory, sha256)


def _result(code: int, answer: bytes, directory: Path, sha256: str) -> PreviewResult:
    try:
        said = json.loads(answer.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return PreviewResult("error")
    if code != 0 or not isinstance(said, dict):
        word = said.get("error") if isinstance(said, dict) else None
        return PreviewResult(word if word in _STATES else "error")  # type: ignore[arg-type]
    made = cache.lookup(directory, sha256)
    pages = said.get("pages")
    if made is None or not isinstance(pages, int):
        return PreviewResult("error")
    return PreviewResult("ok", pages, made)
