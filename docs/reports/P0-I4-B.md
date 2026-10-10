# Report — P0-I4 workstream B (Files)

Branch `p0/i4b` (head at the commit that adds this file; p0/i4 workstream A merged in at 3fef48e). Plan: `docs/tickets/P0-I4/README-B.md`.

## Outcome
Objective met: yes. Files attach to records through a content-addressed object store (`fs` default, `s3` tested with moto). The upload service verifies hash and size on the server, dedupes within a scope, runs the quarantine state machine, and writes `File.Uploaded`, `File.Processed` and `File.Rejected` with the `cur_files` row in one unit of work. File slots are declared in LinkML (`tl:file_slots`). `tl file put|get|ls|reconcile` works. Demo path: `just demo P0-I4-B` ran clean on the merged branch; the combined P0-I4 demo is workstream D's. Not verified on a fresh clone.

FANOUT criterion owned by B: "Files: `fs` object store (default) and `s3` (moto-tested); upload with hash verify and dedupe; `File.*` events; `cur_files`; quarantine flag; `tl file put/get`" is met.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T20 `FsObjectStore` | merged | 1 | Review ruling: `put_via_url` and `presign_put` refuse `sha256/` keys (supervisor added, with tests) |
| T21 `S3ObjectStore` | merged | 1 | `presign_put` got the same guard |
| T22 `tl:file_slots` parse and load | merged | 1 | |
| T23 required file slots | merged | 1 | |
| T24 `tl file put|get|ls` | merged | 1 | `get` closes the stream in a `finally` (accepted deviation); report's docstring claim corrected at merge |
| T25 reconciliation and `tl file reconcile` | merged | 1 | Supervisor added the object-vanishes-during-verify case |
| T26 docs | abandoned as a ticket | — | Supervisor wrote the READMEs, AGENTS.md, runbook and demo: mostly security operating rules that needed the final behaviour |

Merged 6, taken over 0, abandoned 1 (T26, reason above). No ticket needed a second review round.

## Supervisor-built pieces (REVIEW-SUPERVISOR-PIECES)
- Schema: `schema/core/files.yaml`, `annotations.yaml` (`tl:file_slots`), `core.yaml`, `schema/fixtures/files/core-record.yaml`; generated DDL and models. Commit d543a9c.
- `tl_core/files/`: `service.py` (upload service), `lifecycle.py`, `queries.py`, `scan.py`, `keys.py`, `errors.py`; `projection/files.py`; the files section of `services/errors.py`; `tl_adapters/objectstore/__init__.py` (factory, `object_secret`); `justfile` and root `conftest.py` (`TL_ENV=dev`).
- Round-2 additions: content-key guards in fs and s3, lost-object restore in `_attach`, vanishing-object case in `reconcile.py`.
- Tests of these: `tests/services/test_file_service.py` (45), `test_file_service_fs.py` (2), `test_reconcile_races.py` (1), `packages/tl-core/tests/test_file_lifecycle.py` (14), `packages/tl-adapters/tests/test_objectstore_guards.py` (3), `test_objectstore_factory.py` (8), `packages/tl-cli/tests/test_cli_file_reconcile_exit.py` (1). Mutation checks on the service, the stores and the reconciliation each failed a test.

## Gates
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright, codegen drift) | green on 3fef48e |
| `just test` | 1932 passed (includes workstream A merged in) |
| `just test-parity`, `just test-tui` | not applicable (no adapter parity suite yet; no TUI change) |
| Schema classification | `schema/**` changes are additive (new class, new annotation doc, fixture); human gate delegated, listed under SCHEMA_APPROVALS |
| Demo `just demo P0-I4-B` | ok |
| Security review of the upload service | changes requested, fixed in 9447efb, verified PASS by the orchestrator |

## Deviations from plan
- T26 (docs ticket) done by the supervisor, see above.
- Workstream A (p0/i4 at fa87594) was merged into `p0/i4b` at the end; two doc conflicts (`packages/tl-core/README.md`, `AGENTS.md`) resolved by keeping both texts.
- Dependencies added: `boto3` (tl-adapters), `moto[s3]` (dev group), per ADR-0002.

## Escalations and decisions
- Review rulings: security findings 1 to 4 (dedupe gate on `available` only; byte-wise token comparison; fail-closed `object_secret`; global rejected-hash check kept with its oracle documented) and the content-key rule for presigned uploads (D14). Decisions D1 to D14 are in README-B.
- For workstream C (carried by the orchestrator): downloads must send `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

## Learnings
Appended: L-P0-I4-B1 to B9 (worktree `uv sync --all-packages`; moto usage and the put_object spy; RawIOBase test doubles; Protocol gaps and staging; stub-plus-reference verification; security review rules; recovery runbook steps need a test; CliRunner swallows exceptions; one invariant per ticket). Implementer proposals declined: T22 (extract a shared `_as_mapping` helper) since two copies are not enough to justify a module; T23 (Edit tool wants a Read first) is tool behaviour, not a project fact.

## Docs
- Runbook: `docs/runbooks/object-store-reconciliation.md`.
- Updated: `packages/tl-adapters/{README,AGENTS}.md`, `packages/tl-core/{README,AGENTS}.md`, `packages/tl-cli/{README,AGENTS}.md`.
- Plan with the published upload-service signatures: `docs/tickets/P0-I4/README-B.md`. Demo: `dev/demos/P0-I4-B.sh`.

## Follow-ups filed (for the next increment or phase)
- EXIF GPS extraction and stripping from the shared rendition (§20.2 privacy); thumbnails, OCR, conversion pipelines (`processing` in slots is declared, nothing runs it).
- ClamAV scanner behind the `Scanner` Protocol, a worker calling `scan_pending` (set `scan_inline=False`), and the admin override for a falsely rejected hash.
- Multipart upload with resume for large files (S3 backend uses one `put_object`, 5 GiB limit).
- P0-I5 (Postgres): unique constraint on `(record_id, slot, revision)`; `cur_files` SQL is dialect-neutral but untested on Postgres.
- Bulk upload by filename pattern, retention class and object lock, `attachments[]` on the record envelope, hardening `iter_keys` into the Protocol if workstream C needs it.
- Bucket lifecycle rule for `staging/` (documented in the runbook).

## Cost notes
Six implementer tickets, six first-round reviews, no retries. The supervisor wrote about 1,400 lines of engine, projector and test code and four reference implementations (kept outside the repo and deleted after the merge).
