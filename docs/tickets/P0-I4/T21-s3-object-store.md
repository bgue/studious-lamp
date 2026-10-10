# P0-I4-T21 — S3 object store (boto3, tested with moto)

Status: merged
Tier: haiku
Labels: adapter
Depends on: — (stub, error types, key validation, dependencies and the provided test are on the base branch)
Branch: `p0/i4b-t21-s3-object-store`

## Goal
`tl_adapters.objectstore.s3.S3ObjectStore` implements the `ObjectStore` Protocol on an S3 bucket through a boto3 client that the
caller supplies, for MinIO or S3 in a real deployment. Tests use moto's in-process mock (`mock_aws`); no MinIO, no network (ADR-0002).
The class, constructor, docstrings and signatures exist; every method marked `raise NotImplementedError` is the work. A provided
test file (24 tests) must pass. Multipart upload is out of scope for Phase 0.

## Brief references (pasted)
> **5.2** Files are immutable too: object keys are content-addressed (SHA-256). A file is never replaced; a new revision references a new object.
> **20.2** Client computes SHA-256 → server returns existing object (dedupe) or presigned multipart URLs → server verifies hash & size.
> **ADR-0002** `s3` (boto3, for MinIO/S3) is tested against moto from PyPI; no ticket may assume a live MinIO.

### Specification (the provided test checks it)
- `boto3` and `moto` are already installed (`packages/tl-adapters/pyproject.toml`, root dev group). Do not add or change dependencies. The module starts with `# pyright: basic` (boto3 has no type stubs); keep it.
- **Keys.** `_full(key) = self._prefix + check_key(key)` (`check_key` from `tl_core.files.keys` raises `InvalidObjectKey`). Every method validates the key through `_full`.
- **`put(key, data, *, size, sha256, content_type)`.** Spool, then verify, then upload. Open `tempfile.SpooledTemporaryFile(max_size=self._spool_max)`; read `data` in chunks of at most 1 MiB, but **never more than `size + 1` bytes in total** (use `min(chunk, size + 1 - count)`), updating a `hashlib.sha256` and a byte count and writing each chunk to the spool. Stop reading once `count > size`. Raise `ObjectIntegrityError` when `count != size` or when the digest differs from `sha256.lower()`; nothing may be uploaded in that case. If `is_content_key(key)` and `self.exists(key)`, return without uploading (a content-addressed object is never replaced; other keys are overwritten). Otherwise `spool.seek(0)` and call `self._client.put_object(Bucket=..., Key=full, Body=spool, ContentType=content_type, ContentLength=size, Metadata={"sha256": <lower-case digest>})`.
- **`get(key)`.** `self._client.get_object(Bucket=..., Key=full)`. A `botocore.exceptions.ClientError` whose `exc.response["Error"]["Code"]` is `"NoSuchKey"`, `"404"` or `"NotFound"` raises `ObjectNotFound(key)` (`from None`); any other `ClientError` propagates. Return a readable binary stream over `response["Body"]`: write a small `io.RawIOBase` subclass (`readable()` returns True; `readinto(buffer)` calls `body.read(len(buffer))` and copies the bytes in; `close()` closes the body) and return `cast(BinaryIO, io.BufferedReader(that))`. It must stream (do not read the whole object into memory) and support `with`.
- **`exists(key)`.** `head_object`; the same three codes mean `False`; other errors propagate.
- **`presign_put/presign_get`.** `self._client.generate_presigned_url("put_object" | "get_object", Params={"Bucket": ..., "Key": full}, ExpiresIn=expires_s)`; for put also pass `HttpMethod="PUT"`.
- **`iter_keys()`.** `self._client.get_paginator("list_objects_v2")`, `paginate(Bucket=..., Prefix=self._prefix)`, collect `item["Key"][len(self._prefix):]` from each page's `Contents` (absent when empty), yield them sorted.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- ruff limits lines to 100 columns (docstrings too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The test file imports `requests` (installed with moto) to PUT to a presigned URL inside moto's mock; that is allowed, add nothing.
- Remove the `STUB (P0-I4-T21)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/types.py (frozen contract; do not change)
class ObjectNotFound(KeyError): ...
class ObjectStore(Protocol):
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None: ...
    def get(self, key: str) -> BinaryIO: ...      # raises ObjectNotFound
    def exists(self, key: str) -> bool: ...
    def presign_put(self, key: str, *, expires_s: int) -> str: ...
    def presign_get(self, key: str, *, expires_s: int) -> str: ...

# packages/tl-core/src/tl_core/files/errors.py (exported from tl_core.files)
class ObjectIntegrityError(ValueError): ...   # size or SHA-256 differs from the declaration; nothing stored
class InvalidObjectKey(ValueError): ...

# packages/tl-core/src/tl_core/files/keys.py
def check_key(key: str) -> str: ...           # returns key or raises InvalidObjectKey
def is_content_key(key: str) -> bool: ...     # key.startswith("sha256/")
```
```python
# packages/tl-adapters/src/tl_adapters/objectstore/s3.py (existing stub; keep every name and signature)
class S3ObjectStore:
    def __init__(self, client: Any, bucket: str, *, prefix: str = "", spool_max: int = 8 * 1024 * 1024) -> None   # implemented
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None
    def get(self, key: str) -> BinaryIO
    def exists(self, key: str) -> bool
    def presign_put(self, key: str, *, expires_s: int) -> str
    def presign_get(self, key: str, *, expires_s: int) -> str
    def iter_keys(self) -> Iterator[str]
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-adapters/src/tl_adapters/objectstore/s3.py`
- `packages/tl-core/src/tl_core/files/errors.py`
- `packages/tl-core/src/tl_core/files/keys.py`
- `docs/tickets/P0-I4/provided/test_objectstore_s3.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-adapters/src/tl_adapters/objectstore/s3.py` (edit)
- `packages/tl-adapters/tests/test_objectstore_s3.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T21.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_objectstore_s3.py.txt packages/tl-adapters/tests/test_objectstore_s3.py`
2. Implement the methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-adapters/tests/test_objectstore_s3.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_objectstore_s3.py.txt packages/tl-adapters/tests/test_objectstore_s3.py
```
Expected: 24 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands, and one sentence on how a real MinIO would be configured (`TL_OBJECT_STORE=s3`, `TL_S3_BUCKET`, `TL_S3_ENDPOINT`; the factory is `tl_adapters.objectstore.make_object_store`, already written). Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if moto cannot be imported.
- Stop rather than change any other file (the Protocol, errors and key validation are not yours to change). Do not add a dependency.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
