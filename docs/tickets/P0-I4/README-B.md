# Increment plan — P0-I4 WS-B Files: object store, upload service, `File.*`, `cur_files`, `tl file`

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §5.2 (files are immutable, content-addressed), §6.2 (`attachments[]`), §8 (attachments row), §20 (slots, upload flow, quarantine, privacy, previews), §24.5 (missing or corrupt objects)
Branch: `p0/i4b` (integration branch `p0/i4`; trunk `claude/wizardly-allen-m2v96s`). Ticket branches `p0/i4b-t<nn>-<slug>`.

## Objective
Files attach to records through a content-addressed object store. An `fs` backend (default; atomic, fsynced, verified writes; `file://`
presigned URLs with an HMAC token) and an `s3` backend (boto3, tested with moto) implement the frozen `ObjectStore` Protocol. An upload
service verifies the client-declared hash and size on the server, dedupes, writes `File.Uploaded` (quarantined) and then
`File.Processed` or `File.Rejected` on a `core.File` stream in the same unit of work that the projector writes the `cur_files` row,
and keeps a quarantined file readable only by its uploader. File slots are declared in LinkML (`tl:file_slots`); `cur_files` gives the
current file per slot; unslotted attachments work. `tl file put|get|ls` drives it from the command line. Out of scope for Phase 0: multipart
resume, EXIF GPS strip (a follow-up, §20.2 privacy), ClamAV (the scanner is a pluggable stub that passes everything), thumbnails and OCR,
bulk upload by filename pattern, retention and object lock, an `attachments[]` column on `cur_core_record` (`cur_files` is the projection).

## Demo
Part of the WS-D demo script; WS-B alone is shown by the CLI (the commands below run on a temporary ledger, `TL_OBJECT_ROOT` in a temp directory):
```
tl init
tl record create --project P123 --title "Valve" --key P123-REC-0001
tl file put --project P123 --record P123-REC-0001 --slot report ./mtr.pdf     # sha256, size, status available
tl file put --project P123 --record P123-REC-0001 --slot report ./mtr.pdf     # same bytes: "already attached"
tl file put --project P123 --record P123-REC-0001 --slot report ./mtr-rev2.pdf  # revision 2 supersedes revision 1
tl file ls  --project P123 --record P123-REC-0001                              # current file per slot (--all shows history)
tl file get --project P123 <file-id> --out ./copy.pdf                          # bytes identical to the upload
tl file reconcile                                                              # object store versus ledger report (T25)
```

## Design decisions (supervisor; none changes the frozen contract in `files/types.py`)
| # | Decision | Why |
|---|---|---|
| D1 | A file is its own ledger stream, `core.File`, stream id = `file_id`; `File.Uploaded` carries `record_id` and `slot` | A record edit and a file upload never contend on the record's `expected_version`; links use the same pattern |
| D2 | `cur_files` has one row per attachment. The current file of a slot is `status = 'available' AND superseded_by IS NULL` | Brief §20: "current file per slot"; history stays queryable; two rows may share one `sha256` (stored once) |
| D3 | Supersession happens at `File.Processed` (payload `supersedes`), not at upload | A quarantined or rejected replacement must not hide the file that is still good |
| D4 | Quarantine lifecycle `quarantined → available | rejected`, `available → rejected`; single source `files/lifecycle.py` | Same shape as the link lifecycle; handlers and projector share it |
| D5 | `FileService(scan_inline=True)` appends `File.Uploaded` and `File.Processed|Rejected` in one unit of work; `scan_inline=False` leaves files quarantined for `scan_pending` (a worker) | Phase 0 scanner passes everything; a slow real scanner changes only the flag |
| D6 | Upload ids are HMAC-signed, expiring tokens carrying the declared actor, scope, record, slot, name, type, size, hash and staging key; no upload-session table | Stateless; avoids a hand-written non-projection table; the ledger records only completed uploads |
| D7 | A presigned PUT targets a `staging/<ulid>` key; `complete_upload` streams the staged bytes through `store.put(content key, …)`, which verifies | The Protocol has no copy or delete; a client can never write an unverified object at a content key |
| D8 | Dedupe without bytes only for a hash already attached **in the same scope**; otherwise the bytes must be shown once (hashed, not re-stored) | Knowing a hash must not grant access to someone else's file |
| D9 | Bytes whose hash a scan rejected are refused for good (`ContentRejectedError`) | A rejected file cannot come back by re-upload or dedupe |
| D10 | Completing the same upload (same record, slot, bytes) twice returns the existing file with `already_attached` | Safe retries; resumable clients |
| D11 | The object-store write happens before the unit of work commits. A rollback leaves an unreferenced object | Harmless (content-addressed); the reconciliation job lists orphans (runbook) |

## Upload-service signatures (for WS-C: REST and MCP; frozen for Phase 0 except by escalation)
Module `tl_core.files.service`. Build once per process: `store = tl_adapters.objectstore.make_object_store()` (env `TL_OBJECT_STORE`,
`TL_OBJECT_ROOT`, `TL_OBJECT_SECRET`, `TL_S3_*`), `service = FileService(store, secret=tl_adapters.objectstore.object_secret())`.
Every method takes an **entered** `UnitOfWork` and never commits; a refusal raises a `ServiceError` before anything is appended.
```python
class RegisterUpload(Command):  # actor, source, scope + the fields below
    record_id: str; slot: str | None = None; filename: str; content_type: str; size: int; sha256: str
class AttachFile(RegisterUpload): ...                      # same fields; attach already-attached bytes without an upload
class CompleteUpload(Command): upload_id: str
class UploadTicket(BaseModel):
    upload_id: str; key: str; exists: bool; upload_url: str | None; expires_at: datetime
class FileResult(BaseModel):
    file_id: str; record_id: str; slot: str | None; revision: int; sha256: str; size: int
    status: str            # quarantined | available | rejected
    deduplicated: bool; already_attached: bool; events: list[Event]
@dataclass
class OpenedFile: info: FileInfo; data: BinaryIO            # caller closes data

class FileService:
    def __init__(self, store: ObjectStore, *, secret: bytes, scanner: Scanner | None = None,
                 slots: FileSlotRegistry | None = None, scan_inline: bool = True,
                 upload_ttl_s: int = 3600, max_unslotted_size: int = 5 * 1024**3,
                 clock: Callable[[], datetime] = utcnow) -> None
    def register_upload(self, uow, cmd: RegisterUpload) -> UploadTicket                         # POST /uploads
    def complete_upload(self, uow, cmd: CompleteUpload, data: BinaryIO | None = None) -> FileResult
                                                    # POST /uploads/{id}/complete, or PUT /uploads/{id}/content with data=request body
    def attach_file(self, uow, cmd: AttachFile) -> FileResult                                   # attach to a slot without bytes
    def scan_file(self, uow, scope: str, file_id: str, *, source: str = "svc:scanner") -> FileResult
    def scan_pending(self, uow, *, scope: str | None = None, limit: int = 100) -> list[FileResult]
    def open_file(self, uow, scope: str, file_id: str, *, actor: str) -> OpenedFile             # GET /files/{id}/content
    def presign_download(self, uow, scope: str, file_id: str, *, actor: str, expires_s: int = 300) -> str
```
Module `tl_core.files.queries` (no store needed): `get_file(uow, scope, file_id) -> FileInfo` and
`list_files(uow, scope, record_id, *, slot=None, current_only=False) -> list[FileInfo]` (`GET /records/{id}/files`).
`FileInfo` fields: `file_id, scope, record_id, slot, revision, sha256, size, content_type, filename, status, deduplicated, superseded_by,
reason, uploaded_by, uploaded_at, processed_at, version`, property `current`.
Module `tl_core.files.required`: `missing_required_files(uow, record_id, *, registry=None, by_state=None) -> list[MissingFile]` (T23; a
workflow guard). Module `tl_core.files.slots`: `FileSlot`, `FileSlotRegistry`, `default_file_slots()` (T22).
Errors (all `ServiceError`, in `tl_core.services.errors`): `RecordNotFoundError`, `RecordVoidedError`, `UnknownSlotError`,
`FileTypeNotAcceptedError`, `FileTooLargeError`, `ContentRejectedError`, `UploadTokenError`, `UploadIncompleteError`,
`UploadVerificationError`, `UnknownFileError`, `FileQuarantinedError`, `FileRejectedError`, `ObjectMissingError`,
`InvalidFileTransitionError`. Suggested HTTP mapping: 404 not-found, 409 voided, 413 too large, 415 type, 400 token/verification/incomplete,
403 quarantined (non-uploader), 410 rejected, 422 unknown slot, 503 object missing.
Event payloads (`core.File` stream, `File.*` per `03` §8): `File.Uploaded {file_id, record_id, slot, revision, sha256, size, content_type,
filename, status: "quarantined", deduplicated}`; `File.Processed {file_id, status: "available", report, supersedes[]}`;
`File.Rejected {file_id, status: "rejected", reason, report}`. The scan events' actor is `svc:scanner`.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `schema/core/files.yaml` (`File` → `cur_files`, `FileStatus`, slot enums), `tl:file_slots` in `annotations.yaml`, fixture `schema/fixtures/files/core-record.yaml`, regenerated DDL and models | `schema/**` (human gate; delegated, §20) | Orchestrator | built |
| S2 | Upload service (`files/service.py`): hash and size verification, dedupe, quarantine state machine, `File.*` events in the slot-attachment unit of work, token signing | Hash verification, dedupe and quarantine are the security-relevant core of §20 | Orchestrator | built (38 tests; 8 mutations caught) |
| S3 | `FileProjector` (`projection/files.py`), `files/lifecycle.py`, scanner seam, error types, key validation, object-store factory | The projector carries supersession semantics; the reference was needed at once for the service tests | Orchestrator | built (14 lifecycle tests) |
| S4 | Stubs and provided tests for T20–T23; reference implementations kept outside the repo until the tickets merge | Test scaffolds | — | built |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T20 | `FsObjectStore` (atomic verified writes, presigned file URLs) | H | S3 | ready (batch 1) | |
| T21 | `S3ObjectStore` (boto3, moto) | H | S3 | ready (batch 1) | |
| T22 | `tl:file_slots` parse and load (`files/slots.py`) | H | S1 | ready (batch 1) | |
| T23 | Required file slots: missing list (`files/required.py`) | H | S2 | ready (batch 1) | |
| T24 | `tl file put|get|ls` CLI | H | T20, T22, S2 | draft (batch 2) | |
| T25 | Reconciliation: referenced hashes versus the store (`files/reconcile.py`) and `tl file reconcile` | H | T20 | draft (batch 2) | |
| T26 | Docs: package READMEs and AGENTS.md for the object store and files | H | T24, T25 | draft (batch 2/3) | |

## Order of work
1. Round 1: S1–S4 built; dispatch T20–T23 (disjoint paths).
2. Round 2: merge passed tickets (merge commits), integrate `default_file_slots` into the service tests; write T24–T25 provided tests; dispatch.
3. Round 3: merge, runbook (`docs/runbooks/object-store-reconciliation.md`), READMEs, learnings, report `docs/reports/P0-I4-B.md`; DONE.

## Risks and escalation triggers
- Object bytes are written before the database commit (D11): an orphan after rollback. Mitigation: reconciliation reports orphans; staging objects need a bucket lifecycle rule (the Protocol has no delete).
- The `ObjectStore` Protocol has no list, size or delete; reconciliation uses `iter_keys` on the concrete backends (not in the Protocol). Escalate if WS-C needs `iter_keys` through the Protocol.
- Postgres is not exercised before P0-I5: `cur_files` SQL is dialect-neutral (bound params, no JSON functions), but there is no unique constraint on `(record_id, slot, revision)`; a concurrent double upload could duplicate a revision number. Single-writer SQLite hides it. Note for P0-I5.
- EXIF GPS stripping, multipart/resume and real malware scanning are deferred (see Objective).
- Escalate to the orchestrator for: a change to `files/types.py`, a new dependency beyond boto3/moto, auth semantics for who may read a quarantined file beyond "the uploader".

## Blocked / Decision
(none)
