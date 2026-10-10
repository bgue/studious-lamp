# P0-I7-T01 — Filesystem ArchiveStore (write-once)

Status: ready
Tier: haiku
Labels: adapter
Depends on: P0-I7-S10 (the `tl_core.archive` package, merged into the base of this branch)
Branch: `p0/i7a-t01-fs-archive-store`

## Goal
`tl_adapters.archivestore.FsArchiveStore` stores archive files under a local directory and refuses to ever replace a key. The sealer writes ledger archive
segments into it. A stub exists (`archivestore/fs.py`, methods raise `NotImplementedError`). A provided test file (21 tests) must pass.

## Brief references (pasted)
> **24.3 Backup, ledger archive:** Sealed segments, NDJSON + Parquet, with a signed hash manifest continuing the hash chain. Written to an **independent** bucket/account
> with object lock. A database-independent restore path: everything can be rebuilt from this plus objects.
> **Fanout decision D4:** The ArchiveStore is independent of the record ObjectStore (a different root, write-once). Object lock and WORM in production come later.

### Specification (the provided test checks it)
- `FsArchiveStore(root)` creates `root` (and parents) if missing; `.root` returns it as a `Path`.
- A key is a relative path with `/` separators, for example `segments/000000000001-000000000006/manifest.json`. The file lives at `root/<key>`; parent directories are created
  on demand. A key is **invalid** (raise `ValueError`, from `put_bytes`, `get_bytes` and `exists` alike, before touching the disk) when it is empty, contains `\0` or `\`, starts
  with `/`, or has a segment that is empty, `.`, `..` or starts with `.tmp-` (this also rules out a trailing `/` and `//`).
- `put_bytes(key, data)` is **write-once and atomic**: write the bytes to a temp file in the same directory (`tempfile.mkstemp(dir=..., prefix=TMP_PREFIX)`), flush and `os.fsync`,
  `os.chmod(tmp, 0o444)`, then publish it with `os.link(tmp, final)`. `os.link` fails with `FileExistsError` when the key exists: turn that into
  `ArchiveExistsError(key)` (never overwrite, even for identical bytes). Always remove the temp file afterwards (`finally`, ignoring `FileNotFoundError`), so a failure
  leaves neither the key nor a temp file. Do **not** use `os.rename` or `os.replace`: they overwrite silently.
- `get_bytes(key)` returns the bytes; a missing key raises `KeyError(key)` (not `FileNotFoundError`).
- `exists(key)` is true only for a regular file.
- `list_keys(prefix)` returns every stored key that starts with `prefix` (a plain string prefix, not a directory), sorted ascending, with `/` separators, never including a temp
  file (a name starting with `TMP_PREFIX`). Use `os.walk(self._root)`. An unknown prefix gives `[]`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I7/provided/*.py.txt`; copy the file to `packages/tl-adapters/tests/test_archivestore_fs.py` and do not edit it.
- Keep the stub's names and signatures. Remove the `STUB (P0-I7-T01)` paragraph from the module docstring when you are done.
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- `tl_adapters` is checked by pyright in strict mode: annotate everything, and import `ArchiveExistsError` from `tl_core.archive`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/archive/types.py
class ArchiveStore(Protocol):
    """Write-once byte store for archive files. Phase 0 backend: a local directory (fs).

    put_bytes refuses to overwrite an existing key (object-lock semantics, §24.3).
    """

    def put_bytes(self, key: str, data: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...  # sorted ascending
```
```python
# packages/tl-core/src/tl_core/archive/errors.py (importable as `from tl_core.archive import ArchiveExistsError`)
class ArchiveExistsError(ArchiveError):
    """``put_bytes`` was called for a key that already exists (the archive is write-once)."""
```
```python
# packages/tl-adapters/src/tl_adapters/archivestore/fs.py (the stub you fill in)
TMP_PREFIX = ".tmp-"

class FsArchiveStore:
    def __init__(self, root: Path | str) -> None: ...
    @property
    def root(self) -> Path: ...
    def put_bytes(self, key: str, data: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...
```

## Context (read these, nothing else)
- `packages/tl-adapters/src/tl_adapters/archivestore/fs.py`
- `packages/tl-adapters/src/tl_adapters/archivestore/__init__.py`
- `docs/tickets/P0-I7/provided/test_archivestore_fs.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-adapters/src/tl_adapters/archivestore/fs.py` (edit)
- `packages/tl-adapters/tests/test_archivestore_fs.py` (create: the provided file, unedited)
- `docs/reports/P0-I7/P0-I7-T01.md` (create: your report; commit it)

## Acceptance
```
cp docs/tickets/P0-I7/provided/test_archivestore_fs.py.txt packages/tl-adapters/tests/test_archivestore_fs.py
uv run pytest packages/tl-adapters/tests/test_archivestore_fs.py -q
just check
diff docs/tickets/P0-I7/provided/test_archivestore_fs.py.txt packages/tl-adapters/tests/test_archivestore_fs.py
```
Expected: 21 passed; `just check` clean; `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T01.md` and committed.

## Escalation triggers
- Stop and report *Blocked* if a provided test seems to contradict the specification above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
