# P2-I3-T05c — `tl mat` write verbs (receipt, move, reserve, mto assign)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: T05b (merged), S3 (merged), S4 (merged), r9 glue (`mat_write.py` stub, `register` call in `mat.py`)
Branch: `p2/i3-t05c-cli-writes`

## Goal
The write half of `tl mat`: receive and decide receipts, post the seven stock movements, assign take-off lines to a work package. Every verb builds the module's command model, checks the word with `require_command`, runs the handler in one `open_uow(db)` and prints one line. No new rule: the handlers refuse (their `ServiceError` text is printed by `service_errors()`, exit 1).

## Brief references (pasted)
> Verbs (all `--project P` and `--actor` (default `DEV_ACTOR`), `source="cli"`, scope `project:<P>`; quantities stay text, the model validates):
> - `receipt receive --location L --received-on YYYY-MM-DD --line ITEM:QTY[:HEAT[:CONDITION]] (repeat, 1 to 50) [--po-line KEY] [--supplier TEXT] [--delivery-ref TEXT]` -> `CreateReceipt`; prints `received <number>  <n> lines`.
> - `receipt inspect NUMBER [--notes T]` -> `InspectReceipt`; `receipt accept NUMBER` -> `AcceptReceipt` (`expected_version` = `common.version_of(uow, receipt.id)`); `receipt reject NUMBER --reason T` -> `RejectReceipt`; `receipt void NUMBER --reason T` -> `VoidReceipt`. Each prints `<number> is <state>` read back with `views.receipt_detail`.
> - `move KIND --lot KEY --qty Q --uom U [--from L] [--to L] [--for-cost-code ID] [--for-line LINE_ID] [--reason T] [--person T]` with KIND one of `issue transfer return reserve unreserve adjust scrap` -> the matching `_Batch` command with ONE `Movement`; prints `<kind> <qty> <uom> lot <key>`. `reserve`/`unreserve` take `--for-line` (the `MTOLine` record id).
> - `mto assign --work-package NUMBER LINE_KEY...` (one or more line keys as arguments) -> `AssignMtoLines`; prints `assigned <n> lines to <work package>`.
> Receipt number to record id: `views.receipt_detail(uow.conn(), scope, number).id` (raises `ReceiptNotFoundError`, printed by `service_errors()`).
> `--line` is split on `:`; a bad split or a quantity the model refuses is `fail(...)` (exit 1) via `service_errors()` (pydantic `ValidationError` is already handled there).

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.handlers.receipts: CreateReceipt(po_line, supplier_text, delivery_ref, received_on, location_code, lines: list[ReceiptLineIn]) ; ReceiptLineIn(item_code, qty: str, uom, heat_no, condition="good", serials_text)
#   InspectReceipt(stream_id, expected_version|None, notes) AcceptReceipt(stream_id, expected_version>=1) RejectReceipt(stream_id, expected_version|None, reason) VoidReceipt(same as Reject)
#   handle_create_receipt handle_inspect_receipt handle_accept_receipt handle_reject_receipt handle_void_receipt : (uow, cmd) -> CommandResult
# tl_mod_materials.handlers.movements: Movement(lot_key, qty: str, uom, from_location, to_location, cost_code_id, mto_line_id, reason, person, direction)
#   IssueStock TransferStock ReturnStock ReserveStock UnreserveStock AdjustStock ScrapStock : Command with movements: list[Movement]; handle_<verb>_stock(uow, cmd) -> CommandResult
# tl_mod_materials.handlers.mto: AssignMtoLines(mto_lines: list[str], work_package_number: str); handle_assign_mto_lines(uow, cmd)
# tl_mod_materials.common: version_of(uow, record_id) -> int      tl_mod_materials.views: receipt_detail(conn, scope, number) -> ReceiptDetailView (.id .number .state)
# tl_cli.session: DEV_ACTOR, require_command(uow, command)        tl_cli.derive_support: Project, Actor, fail, service_errors
# tl_cli/mat_write.py (stub): def register(app: typer.Typer) -> None   (called from mat.py; app has sub-groups `receipt`, `mto` via typer.Typer registered_groups; reuse mat_read._group)
# precedent to copy: tl_cli/comm.py `_move` (command build, require_command, handler, read back) lines 278-300
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/mat_write.py`, `packages/tl-cli/src/tl_cli/mat.py`, `packages/tl-cli/src/tl_cli/mat_read.py` (lines 1-30 and 320-345), `packages/tl-cli/src/tl_cli/comm.py` lines 268-345
- `dev/accept/P2-I3/S3.py` (the seed: which items, locations, lots exist; how commands are run)
may explore: the handler files named above (signatures only)

## Allowed paths
- `packages/tl-cli/src/tl_cli/mat_write.py` (edit: fill `register`)
- `dev/accept/P2-I3/T05c.py` (create), `docs/reports/P2-I3/T05c.md` (create)
Not here: `mat.py`, `mat_read.py`, `main.py`, any handler, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T05c.py
```
`T05c.py` (you write it; exit 0; one `PASS <check>` per line) copies `.accept/p2-i3.db` to a temp dir and drives `tl_cli.mat.app` with `typer.testing.CliRunner().invoke(app, [...], obj=<target>)`, project `P123`, actor `user:materials-super` (the seed's super user; check `require_command` accepts it):
(1) `receipt receive` with two `--line` flags creates a receipt (`received P123-RCPT-0002  2 lines`), then `receipt list` shows it Received; `receipt inspect` then `receipt accept` end `Accepted`, and `stock` shows the new lot; (2) a second receipt rejected with `--reason` ends `Rejected`; a third voided ends `Void`; (3) `move transfer` moves part of a lot between two seed locations and `stock` shows both; `move issue` over the on-hand fails exit 1 with the handler's text (no traceback); (4) `reserve` then `unreserve` of an MTO line (line id from the seed ledger; read it with `mto_line_detail` or `views.mto_lines`) changes `lot` output; (5) `mto assign` of a line with no reservation to a work package of the seed succeeds, a line with a reservation exits 1; (6) `receipt receive` with a bad `--line` (`X`) exits 1 and the ledger event count is unchanged; (7) the plain user (`user:plain`) is refused with exit 1 on `receipt receive` (word `materials.receive`).

## Tests to add
None (T11 owns tests).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines. Commit subjects `P2-I3-T05c: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if a verb needs a password or token on the command line, if `require_command` cannot be satisfied by the named actors, or if the diff passes 400 lines (split by verb group and say so).

## Blocked
(implementer writes here)
