# P0-I4-T24 — `tl file put|get|ls`

Status: merged
Tier: haiku
Labels: cli
Depends on: — (service, fs store and slots are merged; the group, helpers and registration are on the base branch)
Branch: `p0/i4b-t24-tl-file-cli`

## Goal
The `tl file` command group attaches a local file to a record, writes a stored file back to disk, and lists a record's files. Each command
parses options, makes calls into `tl_core.files` and prints; no rules live in the CLI (AGENTS.md). The group, its helpers (`_fail`,
`_service_errors`, `_service`), the option declarations and the registration in `main.py` exist; the three command bodies `put`, `get`
and `ls` marked `raise NotImplementedError` are the work. `reconcile` is another ticket (T25) and is not yours. A provided test file
(9 tests) must pass.

## Brief references (pasted)
> **20.2** Client computes SHA-256 (streamed) → POST /uploads (slot, size, hash, type) → server returns existing object (dedupe) or presigned URLs → client uploads → /complete → server verifies hash & size → `File.Uploaded` event; file attached to the record slot (ledgered). **Quarantine:** files are unreadable by others until the scan passes.
> **5.2** Files are immutable: object keys are content-addressed (SHA-256). A file is never replaced; a new revision references a new object.

### Specification (the provided test checks it)
All three commands read the ledger path from `ctx.obj` (a `Path`, set by the root callback from `--db` / `TL_DB`), exactly like `tl record`. Errors: `_fail(message)` prints `error: <message>` on stderr and exits 1. Wrap service calls in `with _service_errors():` so `ServiceError`, `ConcurrencyError` and validation errors become that.
- **`put`.**
  1. `scope = f"project:{project}"`. Media type = `--content-type`, else `mimetypes.guess_type(path.name)[0]`, else `"application/octet-stream"`.
  2. Hash the file with `hashlib.sha256` in 1 MiB chunks; size = `path.stat().st_size`.
  3. `service = _service()` (before opening the unit of work).
  4. `with _service_errors(), open_uow(db) as uow:` (one unit of work for the whole command): `found = get_record(uow, scope, record)`; if `None`, `_fail(f"no record with key {record!r} in project {project!r}")`. Then `ticket = service.register_upload(uow, RegisterUpload(actor=actor, source="cli", scope=scope, record_id=found["id"], slot=slot, filename=path.name, content_type=media, size=size, sha256=<hex digest>))`. Build `complete = CompleteUpload(actor=actor, source="cli", scope=scope, upload_id=ticket.upload_id)`. If `ticket.exists`, `result = service.complete_upload(uow, complete)`; otherwise open the file again in binary mode and `result = service.complete_upload(uow, complete, source_file)`.
  5. After the block, print these lines in this order with `typer.echo`: `file <file_id>`, `slot <slot or ->`, `revision <n>`, `status <status>`, `size <n>`, `sha256 <hex>`, `deduplicated true|false`, and, only when `result.already_attached`, a final line `already attached`.
- **`get`.** If `out.exists()` and not `force`: `_fail(f"{out} already exists; use --force to overwrite it")`. `service = _service()`. `with _service_errors(), open_uow(db, readonly=True) as uow:` call `opened = service.open_file(uow, scope, file_id, actor=actor)`. Then stream `opened.data` into `out` (`out.open("wb")`) in 1 MiB chunks while updating a SHA-256 and a byte count; if anything raises while copying, delete `out` (`unlink(missing_ok=True)`) and re-raise. After copying, if the digest differs from `opened.info.sha256` or the count from `opened.info.size`, delete `out` and `_fail(f"the stored object for {file_id} does not match its recorded SHA-256; see the object-store reconciliation runbook")`. Otherwise print `wrote <out>`, `size <n>`, `sha256 <hex>`.
- **`ls`.** `with _service_errors(), open_uow(db, readonly=True) as uow:` look the record up as in `put` (same `_fail` message when missing), then `files = list_files(uow, scope, found["id"], slot=slot, current_only=not all_files)`. Print one line per file, fields joined by a single TAB, no header: `file_id`, `slot` (or `-`), `revision`, status, `size`, `filename`. The status shown is `superseded` when `info.superseded_by` is set, else `info.status`.
- Imports you need: `hashlib`, `mimetypes` (stdlib); `open_uow` from `tl_adapters.sqlite.uow`; `list_files` from `tl_core.files.queries`; `CompleteUpload`, `RegisterUpload` from `tl_core.files.service`; `get_record` from `tl_core.services.queries`. Keep the existing imports that are still used and remove none that the helpers need.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Tests run with `TL_ENV=dev` (set in the root `conftest.py` and by the provided test): the object-store secret fails closed without it. Do not add any default secret.
- The service `FileService` and everything in `tl_core.files` is final; do not change it. Typer needs `Annotated` option declarations exactly as in the stub.
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`. Remove the `STUB (P0-I4-T24)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/service.py (final)
class RegisterUpload(Command): record_id: str; slot: str | None; filename: str; content_type: str; size: int; sha256: str
class CompleteUpload(Command): upload_id: str
class UploadTicket(BaseModel): upload_id: str; key: str; exists: bool; upload_url: str | None; expires_at: datetime
class FileResult(BaseModel):
    file_id: str; record_id: str; slot: str | None; revision: int; sha256: str; size: int
    status: str; deduplicated: bool; already_attached: bool; events: list[Event]
@dataclass
class OpenedFile: info: FileInfo; data: BinaryIO
class FileService:
    def register_upload(self, uow, cmd: RegisterUpload) -> UploadTicket
    def complete_upload(self, uow, cmd: CompleteUpload, data: BinaryIO | None = None) -> FileResult
    def open_file(self, uow, scope: str, file_id: str, *, actor: str) -> OpenedFile
# packages/tl-core/src/tl_core/files/queries.py (final)
class FileInfo(BaseModel): file_id: str; scope: str; record_id: str; slot: str | None; revision: int; sha256: str; size: int; content_type: str; filename: str; status: str; superseded_by: str | None; ...
def list_files(uow, scope: str, record_id: str, *, slot: str | None = None, current_only: bool = False) -> list[FileInfo]
# packages/tl-core/src/tl_core/services/queries.py
def get_record(uow: UnitOfWork, scope: str, key: str) -> dict[str, Any] | None   # the row has "id"
```
The stub (`packages/tl-cli/src/tl_cli/file.py`) is the other interface: keep every name, option and helper.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/file.py`
- `packages/tl-cli/src/tl_cli/record.py` (the pattern to mirror: `ctx.obj`, `open_uow`, `get_record`, error handling)
- `docs/tickets/P0-I4/provided/test_cli_file.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/file.py` (edit)
- `packages/tl-cli/tests/test_cli_file.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T24.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_cli_file.py.txt packages/tl-cli/tests/test_cli_file.py`
2. Implement the three commands; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_file.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_cli_file.py.txt packages/tl-cli/tests/test_cli_file.py
```
Expected: 9 tests pass, `just check` and `just test` exit 0, `diff` prints nothing. (`just test` also runs T25's tests only if that ticket is merged; with its stub, `tl file reconcile` is not tested.)

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (`tl_core.files`, `main.py`, `file_reconcile.py` are not yours).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
