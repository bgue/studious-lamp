"""The page-1 picture cache: ``<sha256>.png`` files in one private directory (P1-UX2-S4).

The directory is ``$XDG_CACHE_HOME/throughline/preview`` (else ``~/.cache/throughline/preview``),
mode 0700. A file name is the SHA-256 of the document it shows, 64 lower-case hex digits and
``.png``; any other name is never read, written or removed here. The cache holds at most
``MAX_ENTRIES`` pictures and ``MAX_TOTAL_BYTES`` bytes; the oldest are evicted first. The page
count of the document rides inside the PNG (a ``pages`` text chunk), so a hit needs no child.
"""

from __future__ import annotations

import os
import re
import struct
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

MAX_ENTRIES = 200
MAX_TOTAL_BYTES = 64 * 1024 * 1024
PAGES_KEY = "pages"
_NAME = re.compile(r"[0-9a-f]{64}")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_STALE_TEMP_SECONDS = 3600
_TEMP_PREFIX = ".tmp-"
_MAX_HEADER_SCAN = 64 * 1024  # the text chunk comes before the pixels; never read further


def valid_hash(sha256: str) -> bool:
    """True for exactly 64 lower-case hex digits (so no path can be built from the name)."""
    return _NAME.fullmatch(sha256) is not None


def cache_dir(env: dict[str, str] | None = None) -> Path:
    """The cache directory (not created)."""
    source = os.environ if env is None else env
    base = source.get("XDG_CACHE_HOME")
    root = Path(base) if base and os.path.isabs(base) else Path.home() / ".cache"
    return root / "throughline" / "preview"


def ensure_dir(root: Path) -> Path:
    """Create ``root`` (mode 0700) and return it; refuse a link or a directory of someone else."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = os.lstat(root)
    if not os.path.isdir(root) or os.path.islink(root):
        raise OSError(f"the preview cache {root} is not a plain directory")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise OSError(f"the preview cache {root} belongs to someone else")
    if info.st_mode & 0o077:
        os.chmod(root, 0o700)
    return root


def entry_path(root: Path, sha256: str) -> Path | None:
    """The path of the entry for ``sha256``, or ``None`` when the name is not 64 hex digits."""
    if not valid_hash(sha256):
        return None
    return root / f"{sha256}.png"


def lookup(root: Path, sha256: str) -> Path | None:
    """The cached picture for ``sha256`` when there is one: a regular file, never a link."""
    path = entry_path(root, sha256)
    if path is None:
        return None
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not os.path.isfile(path) or os.path.islink(path) or info.st_size == 0:
        return None
    return path


def read_pages(path: Path) -> int | None:
    """The page count stored in a cached PNG, or ``None`` if it has none (bounded read)."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_HEADER_SCAN)
    except OSError:
        return None
    if not data.startswith(_PNG_SIGNATURE):
        return None
    pos = len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"tEXt":
            key, _, value = body.partition(b"\x00")
            if key.decode("latin-1") == PAGES_KEY and value.isdigit():
                return int(value)
        if kind in (b"IDAT", b"IEND"):
            return None
        pos += 12 + length
    return None


def write_entry(root: Path, sha256: str, fill: Callable[[Path], None]) -> Path:
    """Write the entry for ``sha256``: ``fill`` writes a temp file, then it is renamed into place.

    Raises ``ValueError`` for a name that is not 64 hex digits. The rename is atomic, so a reader
    sees the whole picture or none.
    """
    target = entry_path(root, sha256)
    if target is None:
        raise ValueError("a cache name must be 64 hex digits")
    ensure_dir(root)
    fd, temp_name = tempfile.mkstemp(dir=root, prefix=_TEMP_PREFIX, suffix=".png")
    os.close(fd)
    temp = Path(temp_name)
    try:
        fill(temp)
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return target


def evict(
    root: Path, *, max_entries: int = MAX_ENTRIES, max_bytes: int = MAX_TOTAL_BYTES
) -> list[str]:
    """Delete the oldest entries until the cache fits both caps; return the names removed.

    Only files named like an entry are counted or removed, plus half-written temp files older than
    an hour. Anything else in the directory is left alone.
    """
    try:
        listing = list(os.scandir(root))
    except OSError:
        return []
    now = time.time()
    entries: list[tuple[float, int, Path]] = []
    for item in listing:
        path = Path(item.path)
        try:
            info = item.stat(follow_symlinks=False)
        except OSError:
            continue
        if item.name.startswith(_TEMP_PREFIX):
            if now - info.st_mtime > _STALE_TEMP_SECONDS:
                path.unlink(missing_ok=True)
            continue
        if not item.name.endswith(".png") or not valid_hash(item.name[:-4]):
            continue
        if not item.is_file(follow_symlinks=False):
            continue
        entries.append((info.st_mtime, info.st_size, path))
    entries.sort(key=lambda e: (e[0], e[2].name))  # oldest first
    total = sum(size for _, size, _ in entries)
    removed: list[str] = []
    while entries and (len(entries) > max_entries or total > max_bytes):
        _, size, path = entries.pop(0)
        path.unlink(missing_ok=True)
        total -= size
        removed.append(path.name)
    return removed
