"""A polling watcher for a type root (brief 31.1; FANOUT D8): no watchdog dependency.

``snapshot(root)`` reads, for every package directory, the size and modification time of each file
and the bytes of ``type.lock``; two snapshots differ exactly when something a sync could care about
changed. ``watch`` takes a snapshot every ``interval`` seconds and calls ``on_change`` with the
packages that changed. It never registers anything itself: the caller runs ``registry.sync``, which
is idempotent, so a missed or duplicated change only costs a re-validation.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tl_core.extypes.lock import LOCK_NAME
from tl_core.extypes.registry import scan

Signature = tuple[int, int, str]  # (largest mtime_ns, total size, sha256 of type.lock or "")
Snapshot = dict[str, Signature]  # package path relative to the root, posix


@dataclass(frozen=True)
class Change:
    path: str  # package directory relative to the root
    kind: Literal["added", "changed", "removed"]


def package_signature(package: Path) -> Signature:
    newest = 0
    total = 0
    for directory, dirnames, filenames in os.walk(package, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            try:
                stat = (Path(directory) / name).lstat()
            except OSError:
                continue
            newest = max(newest, stat.st_mtime_ns)
            total += stat.st_size
    lock = package / LOCK_NAME
    try:
        lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else ""
    except OSError:
        lock_hash = ""
    return newest, total, lock_hash


def snapshot(root: Path) -> Snapshot:
    """Signature of every package directory below ``root``, keyed by relative path."""
    base = root.resolve()
    return {
        package.relative_to(base).as_posix(): package_signature(package) for package in scan(root)
    }


def diff(before: Snapshot, after: Snapshot) -> list[Change]:
    """Packages added, changed or removed between two snapshots, sorted by path."""
    changes: list[Change] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append(Change(path, "added"))
        elif path not in after:
            changes.append(Change(path, "removed"))
        elif before[path] != after[path]:
            changes.append(Change(path, "changed"))
    return changes


def watch(
    root: Path,
    *,
    interval: float,
    on_change: Callable[[list[Change]], None],
    stop: Callable[[], bool] = lambda: False,
    sleep: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
) -> int:
    """Call ``on_change`` now with every package, then whenever the snapshot changes.

    Stops when ``stop()`` is true after a cycle, or after ``max_cycles`` snapshots. Returns the
    number of snapshots taken. A change that arrives while ``on_change`` runs is seen by the next
    snapshot, because the comparison snapshot is taken before the callback.
    """
    previous: Snapshot = {}
    cycles = 0
    while True:
        current = snapshot(root)
        changes = diff(previous, current)
        previous = current
        cycles += 1
        if changes:
            on_change(changes)
        if stop() or (max_cycles is not None and cycles >= max_cycles):
            return cycles
        sleep(interval)
