"""``type.lock``: the content hashes of every file of a package (brief 31.1, FANOUT D9).

The lock is canonical JSON, ``{"files": {<relative path>: <sha256>}}`` with sorted keys and no
whitespace, listing every regular file of the package except ``type.lock`` itself. The
*content hash* of a package is the sha256 of those canonical bytes. A reader accepts a lock with
other whitespace or key order, because it parses and re-serialises before hashing; ``write_lock``
always writes the canonical form. Signing on publish (brief 31.1) is a follow-up.

Hidden files are listed too. Nothing here follows a symbolic link, and a package larger than
``MAX_FILES`` files or ``MAX_FILE_BYTES`` bytes per file is refused, so a registry that scans a
shared directory cannot be made to read arbitrary or unbounded data.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

from tl_schema.effective import canonical_dump

from tl_core.extypes.types import TypeIssue

LOCK_NAME = "type.lock"
MAX_FILES = 200
MAX_FILE_BYTES = 2 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_lock_bytes(files: dict[str, str]) -> bytes:
    """The canonical bytes of a lock holding ``files`` (relative path to sha256)."""
    return canonical_dump({"files": files}).encode("utf-8")


def content_hash(files: dict[str, str]) -> str:
    """sha256 of the canonical lock bytes: the ``content_hash`` of a registration."""
    return hashlib.sha256(canonical_lock_bytes(files)).hexdigest()


def package_files(path: Path) -> tuple[dict[str, Path], list[TypeIssue]]:
    """Regular files of the package below ``path`` by relative posix path, and layout issues.

    Hidden files are locked like any other (a hidden file is still content). A ``__pycache__``
    directory is a ``layout`` issue, since a package carries no bytecode. A symbolic link,
    too many files, or a file over ``MAX_FILE_BYTES`` is reported as a ``layout`` issue and
    left out.
    """
    found: dict[str, Path] = {}
    issues: list[TypeIssue] = []
    for directory, dirnames, filenames in os.walk(path, followlinks=False):
        here = Path(directory)
        kept: list[str] = []
        for name in sorted(dirnames):
            if name == "__pycache__":
                relative = (here / name).relative_to(path).as_posix()
                issues.append(
                    TypeIssue(kind="layout", path=relative, detail="bytecode is not allowed")
                )
                continue
            if (here / name).is_symlink():
                relative = (here / name).relative_to(path).as_posix()
                issues.append(TypeIssue(kind="layout", path=relative, detail="symbolic link"))
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if name == LOCK_NAME and here == path:
                continue
            file = here / name
            relative = file.relative_to(path).as_posix()
            if file.is_symlink():
                issues.append(TypeIssue(kind="layout", path=relative, detail="symbolic link"))
            elif file.stat().st_size > MAX_FILE_BYTES:
                detail = f"larger than {MAX_FILE_BYTES} bytes"
                issues.append(TypeIssue(kind="layout", path=relative, detail=detail))
            elif len(found) >= MAX_FILES:
                issues.append(
                    TypeIssue(kind="layout", path=relative, detail=f"more than {MAX_FILES} files")
                )
            else:
                found[relative] = file
    return found, issues


def compute_lock(path: Path) -> tuple[dict[str, str], list[TypeIssue]]:
    """The lock the package's files give now, and the layout issues found while listing them."""
    files, issues = package_files(path)
    return {relative: sha256_file(file) for relative, file in sorted(files.items())}, issues


def read_lock(path: Path) -> dict[str, str] | None:
    """The files table of ``path/type.lock``, or ``None`` when the file is absent.

    Raises ``ValueError`` when it is not JSON of the shape ``{"files": {str: str}}``.
    """
    lock = path / LOCK_NAME
    if lock.is_symlink() or not lock.is_file():
        return None
    try:
        data: Any = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"type.lock is not readable JSON: {exc}") from exc
    files: Any = cast("dict[str, Any]", data).get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        raise ValueError('type.lock must look like {"files": {"<path>": "<sha256>"}}')
    table = cast("dict[Any, Any]", files)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in table.items()):
        raise ValueError('type.lock must look like {"files": {"<path>": "<sha256>"}}')
    return {str(k): str(v) for k, v in table.items()}


def lock_issues(path: Path) -> list[TypeIssue]:
    """Differences between ``type.lock`` and the files: missing lock, bad lock, and per file."""
    actual, issues = compute_lock(path)
    try:
        declared = read_lock(path)
    except ValueError as exc:
        return [*issues, TypeIssue(kind="lock", path=LOCK_NAME, detail=str(exc))]
    if declared is None:
        return [*issues, TypeIssue(kind="lock", path=LOCK_NAME, detail="type.lock is missing")]
    for relative in sorted(set(declared) | set(actual)):
        if relative not in actual:
            detail = "listed in type.lock but the file is missing"
        elif relative not in declared:
            detail = "not listed in type.lock"
        elif declared[relative] != actual[relative]:
            detail = "hash differs from type.lock"
        else:
            continue
        issues.append(TypeIssue(kind="lock", path=relative, detail=detail))
    return issues


def write_lock(path: Path) -> str:
    """Write the canonical ``type.lock`` for the files now present; returns the content hash."""
    files, issues = compute_lock(path)
    if issues:
        raise ValueError("; ".join(f"{i.path}: {i.detail}" for i in issues))
    (path / LOCK_NAME).write_bytes(canonical_lock_bytes(files))
    return content_hash(files)
