# P2-I3-T06j — Receipt entry: attach the MTR file after the receipt is saved

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: S6, T06e, T06i (merged); D42, D46
Branch: `p2/i3-t06j-mtr-upload`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
`ReceiptEntryScreen` saves `CreateReceipt` and then only tells the user to attach the MTR elsewhere (D42). After this ticket the form has one optional input, `MTR file`, a local path. On a good save with a path typed, the screen attaches that file to the new receipt in slot `mtr` through `client.attach_record_file` (S6) and the status line says so. The path is optional because a receipt may be booked before the certificate arrives.

## Brief references (pasted)
> S6 (merged): `ClientInterface.attach_record_file(record_id, path, *, slot=None, content_type=None) -> FileResult`. `CreateReceipt` returns a `CommandResult` whose `stream_id` is the receipt record id and `key` its number. A hidden or missing record raises `RecordNotFoundError`; no word raises `ForbiddenError`; an unreadable path raises `FileNotFoundError` before any write; a `rejected` FileResult is returned, not raised. After Accept only certificate and photo files attach (not relevant here).
> Existing status texts (receipt_entry_text.py): `MTR_SENTENCE = "Attach the MTR on the receipt (tl file put, slot mtr)."`, `saved_text(number) -> "Saved {number}. {MTR_SENTENCE}"`.

## Interfaces (names are the contract)
```python
# receipt_entry_text.py (Textual-free; add)
MTR_FIELD = ("mtr", "MTR file")          # NOT part of HEADER_FIELDS: check_header and build_command stay as they are
def saved_attached_text(number: str, name: str) -> str:    # "Saved {number}. MTR {name} attached."
def saved_not_attached_text(number: str, reason: str) -> str:   # "Saved {number}. MTR not attached: {reason}. " + MTR_SENTENCE
def check_mtr_path(raw: str) -> str | None:   # None when blank or the path is a readable file; else "No such file: {raw}" (a directory counts as no file)
# widgets/receipt_entry.py: in compose, one Input(id="h-mtr") after the header fields, label from MTR_FIELD; action_save changes as below.
```
Save flow in `action_save`, in this order: (1) the existing header/count checks; (2) `check_mtr_path(raw)`: a non-None answer is shown on the form as a field error line and nothing is saved (a typo must not book a receipt and then lose the file); (3) `CreateReceipt`; (4) with a path, `attach_record_file(result.stream_id, Path(raw).expanduser(), slot="mtr")`. Outcomes: status `available` -> `saved_attached_text`; `quarantined` -> same text (the scan finishes later); `rejected` -> `saved_not_attached_text(number, "the file was rejected")`; a `CLIENT_ERRORS` exception or `OSError` -> `saved_not_attached_text(number, describe_error(exc))`. In every outcome after step 3 the lines are cleared and the receipt stays saved. A blank path keeps today's `saved_text`. Use `result.key or result.stream_id` for the number as now.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/receipt_entry.py` (compose, `action_save`, `_show_errors`, `say`)
- `packages/tl-tui/src/tl_tui/receipt_entry_text.py`
- `packages/tl-tui/tests/fakes_actions.py` (the fake `attach_record_file` and how it fails for an unknown record)
- `dev/accept/P2-I3/T06e.py` (extend), `dev/accept/P2-I3/S6.py` (how a file and an actor are set up)
- `docs/tickets/P2-I3/text-contracts.md` (Receipt entry bullet only)
may explore: none

## Allowed paths
- `packages/tl-tui/src/tl_tui/receipt_entry_text.py`, `packages/tl-tui/src/tl_tui/widgets/receipt_entry.py`
- `dev/accept/P2-I3/T06e.py`
- `docs/tickets/P2-I3/text-contracts.md` (Receipt entry bullet), `docs/reports/P2-I3/T06j.md` (create)
No test file (T11). No client, route or schema change. No new dependency.

## Acceptance (run once; no pytest)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06e.py
uv run python dev/accept/P2-I3/S6.py
```
Expected: exit 0 each. Extend `T06e.py` (one `PASS` line each, fake client): a good save with a real temp file records `(receipt id, name, "mtr")` and the status reads `Saved <n>. MTR <name> attached.`; a good save with no path attaches nothing and keeps `saved_text`; a missing path shows `No such file: ...` and no receipt is booked; a fake that raises `RecordNotFoundError` on attach leaves the receipt saved and the status names `MTR not attached`; the lines are cleared in the last three cases that saved. Also one real-ledger check over a copy of `.accept/p2-i3.db` with `EmbeddedClient`: save then attach, then `list_record_files(receipt id)` shows slot `mtr` (set `TL_ENV=dev`; copy how S6.py builds the client). Save an SVG of the form with the field to `.accept/shots/T06j-<w>.svg` like T06e does.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`, <= 60 lines) plus the output of each acceptance command (<= 5 lines each). More than 5 files changed means stop and say why.
Commit subjects `P2-I3-T06j: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report Blocked if `result.stream_id` is not the receipt record id, or the fake and the embedded client disagree on the exceptions above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
