"""A cheap fingerprint of the definition files in a directory (P2-PERF).

The workflow and expected-link definitions are read from the schema directory "on every call, so
an edited file takes effect at once" (``workflow.provider``). Parsing thirteen YAML files on every
call costs over 100 ms, and a record screen asks several times. The fingerprint (name, size and
modification time of each file, one ``stat`` per file) lets a reader parse again only when a file
was added, removed or edited, so the rule stays and the cost goes.
"""

from __future__ import annotations

from pathlib import Path

Signature = tuple[tuple[str, int, int], ...]


def signature(directory: Path, pattern: str = "*.yaml") -> Signature:
    """``(name, size, mtime_ns)`` of every matching file of ``directory``, sorted by name; empty
    for a directory that does not exist."""
    if not directory.is_dir():
        return ()
    found: list[tuple[str, int, int]] = []
    for path in directory.glob(pattern):
        try:
            info = path.stat()
        except OSError:
            continue  # gone since the listing: the next call sees the difference
        found.append((path.name, info.st_size, info.st_mtime_ns))
    return tuple(sorted(found))
