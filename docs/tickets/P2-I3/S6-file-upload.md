# P2-I3-S6 — Attach a local file to a record through the client (ClientInterface, EmbeddedClient, ApiClient, fake)

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core-module, api, tui
Depends on: T04b, T06e (merged); decision Q8 = YES (r10)
Branch: `p2/i3-s6-file-upload`  (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
`ClientInterface` can read files (`list_record_files`, `fetch_file`) but cannot write one (D42), so the receipt entry screen cannot attach the MTR. After this piece one client call attaches a local file to a record, on the embedded client (in-process, the TUI today), the HTTP client and the fake, with the same access, hidden-record and error behaviour as the HTTP upload flow. A follow-up ticket (T06j, not this piece) wires the receipt entry screen to it.

## Brief references
> Upload protocol (brief 20.2, `tl_core.files.service`): `RegisterUpload` -> `UploadTicket`; bytes needed unless `ticket.exists`; `complete_upload` -> `FileResult` (`status` quarantined | available | rejected). `ApiClient.upload_file(scope, record_id, path, *, slot=None, content_type=None) -> FileResult` already does the whole flow over HTTP (`tl_api/client/files.py:218`); the CLI `tl file put` uses it.
> A file attaches to a record the actor may write; a record the viewer cannot read answers as one that does not exist (ADR-0016): no error text that reveals it. Authorization is closed for agents: no new route. The existing routes (`POST /uploads`, `PUT /uploads/{id}/content`, `POST /uploads/{id}/complete`) are reused.
> The materials receipt: `ReceiptFileView.slot == "mtr"`; `mtr_required` and `mtr` `missing|present` on `ReceiptDetailView`; Accept is refused without the MTR (S3). `CreateReceipt` goes through `client.materials_command`; the new receipt's record id must be readable by the screen after a save: state in the report how (the command result, or `list_materials_receipts`), and add it if the result lacks it only when that is a default-valued field.

## Interfaces (names are the contract; T06j and the web twin call it)
```python
# ClientInterface (packages/tl-tui/src/tl_tui/client.py), next to list_record_files / fetch_file
def attach_record_file(
    self, record_id: str, path: Path, *, slot: str | None = None, content_type: str | None = None
) -> FileResult: ...
    # Hash and register the file at `path`, send the bytes unless the store has them, complete, return the FileResult.
    # A hidden or missing record raises RecordNotFoundError (same class the other record calls raise); an actor without the word raises the
    # ForbiddenError the HTTP flow maps to 403; an unreadable `path` raises FileNotFoundError before any write; a `rejected` FileResult is returned, not raised.
```
- `EmbeddedClient`: run the same `FileService` register/complete steps as the route handlers, in-process, with `self.actor` and the client's unit of work (`_file_service()` already picks the service; no store of its own making); scope from the record (`queries.get_record_by_id` under the viewer, as `list_record_files`). No store configured: `BodyStoreUnavailableError` as `fetch_file`.
- `ApiClient` (`tl_api/client/files.py`): the method resolves the record's scope with the existing record read, then calls `upload_file(scope, record_id, path, slot=slot, content_type=content_type)`. Do not duplicate the hash/register flow; reuse `upload_file`.
- Fake (`packages/tl-tui/tests/fakes_actions.py`, where `add_record_file` and `list_record_files` live; any other class that implements `ClientInterface` gets the method or inherits it): records `(record_id, path.name, slot)`, appends a `FileInfo` so `list_record_files` shows it, returns a `FileResult`; unknown record raises `RecordNotFoundError`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/client.py` (files block), `embedded.py` (`list_record_files`, `_file_service`, `fetch_file`)
- `packages/tl-api/src/tl_api/client/files.py`, `packages/tl-api/src/tl_api/routes/files.py` (what the routes check before registering)
- `packages/tl-core/src/tl_core/files/service.py` (`RegisterUpload`, `AttachFile`, `FileService`)
- `packages/tl-tui/tests/fakes_actions.py`
- `docs/reports/P2-I3/T04b.md`, `T06e.md` (D42 context)
may explore: `packages/tl-cli/src/tl_cli/` for `tl file put`; `tests/api/test_client_roundtrip.py` (the pins that list client methods)

## Allowed paths
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py`; `packages/tl-api/src/tl_api/client/files.py`
- `packages/tl-tui/tests/fakes_actions.py` (and `fakes.py` only if the fake class that must carry the method is there)
- `packages/tl-modules/materials/src/tl_mod_materials/` only if the receipt record id needs a default-valued field on a command result (say so in the report)
- Consequential pins (rule 12): a test that lists client methods and breaks only for the new name, updated and listed (`tests/api/test_client_roundtrip.py`, `packages/tl-tui/tests/test_fakes.py` are the likely ones)
- `dev/accept/P2-I3/S6.py` (create), `docs/reports/P2-I3/S6.md` (create)
No route, no schema, no new dependency, no change to `FileService` behaviour.

## Acceptance (run once; no pytest; tests are T11's)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/S6.py
just gate tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_fakes.py packages/tl-api/tests/test_auth_review.py tests/tools/test_no_sqlite_imports.py
```
`S6.py` (exit 0, one `PASS <check>` per line; sqlite copy of the seed; Postgres too when `TL_PG_URL` is set; give the embedded client an object store as `dev/accept/P2-W0` scripts that read files do): create a receipt through `materials_command(CreateReceipt)` as a person who may; its `mtr` is `missing`; `attach_record_file(receipt_id, tmp.pdf, slot="mtr")` returns a `FileResult` with status `available` (or `quarantined` as the service says; assert what it returns and say so); `receipt_detail.mtr` is `present` and `list_record_files` lists it with slot `mtr`; the receipt now Inspects and Accepts (the two lots exist); a second call with the same bytes is `already_attached` or `deduplicated`, no second event; a record id the viewer cannot read and a made-up id both raise `RecordNotFoundError` with the same text, and write no event; a person without the write word is refused and writes no event; a missing path raises `FileNotFoundError` and writes nothing; the same call through `ApiClient` (in-process app client as `tests/api` does) and the fake return equal `model_dump` shapes for the fields they share; the method exists on all client classes.

## Tests to add
None under `tests/` (T11). Guards for T11 in the report (3 lines, `file:line`): the hidden-record check before the register, the scope taken from the record (not the caller), the write-word check.

## Report requirements
Piece report (≤ 60 lines): deviations first; how the screen gets the new receipt id; pins changed; acceptance output (≤ 5 lines per command); builder return ≤ 15 lines in Code 92.
Commit subjects `P2-I3-S6: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
Stop and write *Blocked* if: the in-process flow needs a change to `FileService` or a route; the embedded client has no way to reach an object store in the TUI's real start-up (say which setting a person must make); a hidden record's refusal differs in text or status from a missing one; or another package's public interface must change.

## Blocked
(builder writes here)

## Decision
(supervisor writes here)
