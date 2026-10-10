# P0-I4-T20 — Filesystem object store

Status: merged
Tier: haiku
Labels: adapter
Depends on: — (stub, error types, key validation and the provided test are on the base branch)
Branch: `p0/i4b-t20-fs-object-store`

## Goal
`tl_adapters.objectstore.fs.FsObjectStore` stores content-addressed files under a root directory: atomic, fsynced, verified writes;
reads; existence checks; `file://` presigned URLs with an HMAC token and expiry; and a sorted key listing. It is the default object
store in dev and in every test (ADR-0002: no MinIO). The class, constructor, docstrings and signatures exist; every method marked
`raise NotImplementedError` is the work. A provided test file (37 tests) must pass. The upload service (supervisor) and the `tl file`
CLI use this class.

## Brief references (pasted)
> **5.2** Files are immutable too: object keys are content-addressed (SHA-256). A file is never replaced; a new revision references a new object.
> **20.2** Client computes SHA-256 → server verifies hash & size. **Quarantine:** files are unreadable by others until the scan passes.
> **ADR-0002** Object store adapter has two backends: `fs` (content-addressed files under `dev/data/objects/`, default in dev and in every test) and `s3`. Presigned URLs in `fs` mode are `file://` paths plus a signed token.

### Specification (the provided test checks it)
- **Layout.** `path_for(key)` is `root / check_key(key)`; `check_key` raises `InvalidObjectKey` for an unsafe key. A content key looks like `sha256/ab/cd/<digest>`; a staging key like `staging/<ulid>`. Every method that takes a key validates it first (so `exists`, `get`, `put`, `presign_*` all raise `InvalidObjectKey` for `""`, `/abs`, `../x`, `a//b`, `a/./b`, `.hidden`, `a b`, `a\b`).
- **`put(key, data, *, size, sha256, content_type)`.** Write to a temporary file in `root/.tmp` (create the directory; use `tempfile.mkstemp(dir=...)`), reading `data` in 1 MiB chunks and updating a `hashlib.sha256` and a byte count. Read **at most `size + 1` bytes** in total (never read an endless stream to the end). Then `flush()` and `os.fsync(fd)` the temporary file. Then verify: the count must equal `size` and the digest must equal `sha256.lower()`; otherwise raise `ObjectIntegrityError` (message says what differed). Only after verification create the parent directories and move the temporary file to its final path with `os.replace`, then fsync the parent directory (open it with `os.open(dir, os.O_RDONLY)`, `os.fsync`, `os.close`). In every outcome (success, mismatch, an exception from `data.read`) the temporary file must be gone: use `try/finally` with `tmp.unlink(missing_ok=True)`.
- **Never replace a content key.** If `key` starts with `sha256/` (`is_content_key(key)`) and the final file already exists, still verify the new bytes (a mismatch still raises) but do **not** call `os.replace`; leave the existing file untouched (same inode, same mtime). Other keys (e.g. `staging/...`) are overwritten by `os.replace`.
- **`get(key)`.** `path.open("rb")`; `FileNotFoundError`, `IsADirectoryError` or `NotADirectoryError` raise `ObjectNotFound(key)` (`raise ... from None`). Return type is `BinaryIO`: use `typing.cast`.
- **`exists(key)`.** `path_for(key).is_file()` (a directory is not an object).
- **`presign_put/presign_get(key, *, expires_s)`.** `expiry = int(self._clock()) + expires_s`. URL = `"file://" + urllib.parse.quote(str(path_for(key).resolve())) + f"?op={op}&exp={expiry}&sig={sig}"` where `op` is `put` or `get` and `sig = hmac.new(secret, f"{op}\n{key}\n{expiry}".encode(), hashlib.sha256).hexdigest()`.
- **`redeem(url, *, op)`.** Parse with `urllib.parse.urlsplit` and `parse_qs`. Raise `PresignInvalid` when `op`, `exp` (must be an int) or `sig` is missing or malformed, when the scheme is not `file`, when the URL's `op` differs from the requested `op`, when the unquoted path is not inside `self._root.resolve()` (use `Path.relative_to`; the relative path is the key), when the key fails `check_key`, or when `sig` differs from the expected signature (compare with `hmac.compare_digest`). Only after the signature verifies, raise `PresignExpired` if `exp < int(self._clock())` (so a URL is still valid during its last second). Return the key.
- **`put_via_url(url, data)`.** `key = redeem(url, op="put")`, then write `data` to `path_for(key)` with the same temporary-file, fsync and `os.replace` steps as `put`, but with no size or hash check (the upload service verifies staged bytes later) and always replacing. Share one private writer between `put` and `put_via_url`.
- **`get_via_url(url)`.** `get(redeem(url, op="get"))`.
- **`iter_keys()`.** Walk `root` (nothing if it does not exist), skip the top-level `.tmp` directory, yield posix relative paths of every file, sorted.
- `content_type` is accepted and ignored by this backend.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-adapters/src`; ruff limits lines to 100 columns (docstrings too). Run `uv run ruff format` before committing.
- `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I4-T20)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/types.py (frozen contract; do not change)
class ObjectNotFound(KeyError): ...
def object_key(sha256_hex: str) -> str: ...   # "sha256/<aa>/<bb>/<digest>"
class ObjectStore(Protocol):
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None: ...
    def get(self, key: str) -> BinaryIO: ...      # raises ObjectNotFound
    def exists(self, key: str) -> bool: ...
    def presign_put(self, key: str, *, expires_s: int) -> str: ...
    def presign_get(self, key: str, *, expires_s: int) -> str: ...

# packages/tl-core/src/tl_core/files/errors.py (exported from tl_core.files)
class ObjectIntegrityError(ValueError): ...   # size or SHA-256 differs from the declaration; nothing stored
class InvalidObjectKey(ValueError): ...
class PresignError(ValueError): ...
class PresignInvalid(PresignError): ...
class PresignExpired(PresignError): ...

# packages/tl-core/src/tl_core/files/keys.py
def check_key(key: str) -> str: ...           # returns key or raises InvalidObjectKey
def is_content_key(key: str) -> bool: ...     # key.startswith("sha256/")
```
```python
# packages/tl-adapters/src/tl_adapters/objectstore/fs.py (existing stub; keep every name and signature)
class FsObjectStore:
    def __init__(self, root: Path, *, secret: bytes, clock: Callable[[], float] = time.time) -> None   # implemented
    @property
    def root(self) -> Path                                                                              # implemented
    def path_for(self, key: str) -> Path
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None
    def get(self, key: str) -> BinaryIO
    def exists(self, key: str) -> bool
    def presign_put(self, key: str, *, expires_s: int) -> str
    def presign_get(self, key: str, *, expires_s: int) -> str
    def redeem(self, url: str, *, op: Literal["put", "get"]) -> str
    def put_via_url(self, url: str, data: BinaryIO) -> None
    def get_via_url(self, url: str) -> BinaryIO
    def iter_keys(self) -> Iterator[str]
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-adapters/src/tl_adapters/objectstore/fs.py`
- `packages/tl-core/src/tl_core/files/errors.py`
- `packages/tl-core/src/tl_core/files/keys.py`
- `docs/tickets/P0-I4/provided/test_objectstore_fs.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-adapters/src/tl_adapters/objectstore/fs.py` (edit)
- `packages/tl-adapters/tests/test_objectstore_fs.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T20.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_objectstore_fs.py.txt packages/tl-adapters/tests/test_objectstore_fs.py`
2. Implement the methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-adapters/tests/test_objectstore_fs.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_objectstore_fs.py.txt packages/tl-adapters/tests/test_objectstore_fs.py
```
Expected: 37 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (the Protocol, errors and key validation are not yours to change).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
