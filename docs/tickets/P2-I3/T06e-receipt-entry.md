# P2-I3-T06e — receipt_entry_text.py and ReceiptEntryScreen (book a delivery); item library crumb

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06b (merged), T06a (merged), T04b (merged), T06c (merged)
Branch: `p2/i3-t06e-receipt-entry`

## Goal
A form screen to book a delivery: header fields, a list of up to 50 lines, `Ctrl+S` sends `CreateReceipt` through `client.materials_command`. All text and validation live in a Textual-free module, so the web twin reuses them. Unregistered (no nav entry, no `app.py` change). Screenshots as D36.
Also, one line in the merged item library: its company-level breadcrumb reads ` › Items` (empty project segment); the other company-level logs say `Company`.

## Decisions that shape this ticket (supervisor, r9)
- D42: the client has no file-upload call (`ClientInterface` has no register/complete upload), so the MTR is NOT attached from this screen. After a save the status line names what is left: `Saved <number>. Attach the MTR on the receipt (tl file put, slot mtr).` The screen has no MTR field. Open question Q8 (a client upload method, a builder piece) is the orchestrator's.
- The lines are entered in a small entry row (Item, Qty, Heat, Condition inputs) and added to a list with `Enter` in the last input; `Ctrl+D` removes the highlighted line. No 50-cell grid.

## Brief references (pasted)
> Contract: `docs/tickets/P2-I3/text-contracts.md` "Shape every module follows" (module rules), "receipt_entry_text.py: form field list, line validation messages, status-line texts". Layout skill `tui-layout`: labels left, one value per line, errors under the field in words, `—` never typed into a field.
> Header fields: PO line (key; completion from `list_materials_po_lines(project, q=text)`, shown as hint lines under the field, max 5; choosing nothing is allowed), Supplier (text; filled from the PO line when chosen and empty), Delivery ref, Received on (default today, `YYYY-MM-DD`), Location (code; must be one of `list_materials_locations(project)` codes; hint lines the same way).
> A line: Item code (must be a code in `list_materials_items(project=project)`), Qty (positive decimal text, at most 3 decimals), Heat (optional), Condition (default `good`; one of `good damaged wrong_item nonconforming`, the `ConditionCode` list; shown through `humanize` as `receipt_text` does). UOM is shown read-only from the item (`unit_label`). 1 to 50 lines.
> Messages (words, not codes): `Pick a location of this project.`, `Item <code> is not in this project's library.`, `Quantity must be a positive number.`, `Received on must be a date, YYYY-MM-DD.`, `Add at least one line.`, `A receipt holds at most 50 lines.`
> Save: build `CreateReceipt(actor=<client actor>, source="tui", scope=f"project:{project}", po_line=..., supplier_text=..., delivery_ref=..., received_on=..., location_code=..., lines=[ReceiptLineIn(...)])` and call `client.materials_command("CreateReceipt", cmd)`; a `CLIENT_ERRORS` refusal goes to the status line via `describe_error`, the form stays open with what was typed.
> Module API (names are the contract; W = web twin): `HEADER_FIELDS` W, `LINE_FIELDS` W, `check_header(values, locations, today) -> list[tuple[str,str]]` W (field, message), `check_line(values, items) -> list[tuple[str,str]]` W, `line_summary(line, uom) -> str` W, `KEYS` W (`Ctrl+S save  Enter add line  Ctrl+D remove line  Esc close`), `saved_text(number) -> str` W, `build_command(header, lines, *, actor, project) -> CreateReceipt` W (pure; imports the command model only).
> Allowed imports in the text module: `tl_mod_materials.handlers.receipts` (command models), `tl_mod_materials.views`, `tl_tui.layout`, `tl_tui.text`, `tl_tui.materials_text`, `tl_tui.display`; never `textual`.

## Interfaces (verbatim from repo at the branch point)
```python
# ClientInterface: list_materials_po_lines(project, *, q=None, limit=1000) -> list[PoLineView]  list_materials_locations(project, ...) -> list[LocationView]
#   list_materials_items(*, project=None, limit=1000) -> list[MaterialItemView]   materials_command(name: str, cmd: Command) -> CommandResult
# PoLineView: key po_number line_no item_code item_title qty_ordered qty_received uom promised_date supplier_text   LocationView: code title kind depth parent_code lots lines ...
# CreateReceipt(po_line: str|None, supplier_text: str="", delivery_ref: str|None, received_on: str (YYYY-MM-DD), location_code: str, lines: list[ReceiptLineIn] 1..50)
# ReceiptLineIn(item_code, qty: str, uom: str|None, heat_no: str|None, condition: str="good", serials_text: str|None)
# the rule behind: a receipt line's item must equal the PO line's item when a PO line is named (S3 D20); the handler refuses otherwise and its text reaches the status line
# shape to copy: widgets/setting_form.py (Ctrl+S, Esc, Inputs, status text) and widgets/log_screen.py only for CLIENT_ERRORS/say; screens in dev/accept/P2-I3/T06b.py (TlApp host, settle, screen_text, screenshots)
```

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/receipt_text.py` (the module shape and labels), `packages/tl-tui/src/tl_tui/widgets/setting_form.py` (whole; the form precedent)
- `dev/accept/P2-I3/T06b.py` (whole: seed copy, EmbeddedClient, TlApp host, screenshots; copy its helpers), `packages/tl-tui/src/tl_tui/widgets/item_library.py` lines 55-70
may explore: `widgets/form_fields.py`, `tl_tui/errors.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/receipt_entry_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/receipt_entry.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/item_library.py` (edit: `log_project` returns `self.project or "Company"`, nothing else)
- `dev/accept/P2-I3/T06e.py` (create), `docs/reports/P2-I3/T06e.md` (create)
Not here: `app.py`, `commands.py`, `client.py`, `receipt_log.py`, `layout.py`, any test file. Changing T06c's acceptance (`dev/accept/P2-I3/T06c.py`) is a consequential pin only if it asserts the empty crumb: update that one assertion and list it in the report.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06e.py
uv run python dev/accept/P2-I3/T06c.py
```
`T06e.py` (you write it; exit 0; one `PASS <check>` per line): (1) text: each message above fires from `check_header`/`check_line` on a bad value and not on a good one; `build_command` of two lines gives a `CreateReceipt` that validates; `import tl_tui.receipt_entry_text` leaves `textual` out of `sys.modules` (fresh subprocess); no `None` or bare `-` in any text. (2) screen, over a copy of the seed with an `EmbeddedClient` (as T06b.py), project `P123`, at 80x30 and 170x40: type a PO line key of the seed (read one with `list_materials_po_lines`), Location `L2`, add two lines of seed items (`Enter`), `Ctrl+S`: the status line says `Saved P123-RCPT-0002` (and the MTR sentence), `list_materials_receipts("P123")` shows it in state Received with 2 lines; a bad location leaves the form open with `Pick a location of this project.`; `Ctrl+D` removes a line; Esc closes. Save `app.export_screenshot(title="New receipt")` to `.accept/shots/T06e-entry-80.svg` and `-170.svg`. (3) `T06c.py` still passes and its company screen crumb reads `Company › Items`.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the screenshot paths. Commit subjects `P2-I3-T06e: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if the form needs a client method that is missing (file upload is known: do not add it), if the text module would need `textual`, if the diff passes 400 lines (then ship the text module and a minimal screen and say what is left), or a name listed under Interfaces is missing.

## Blocked
(implementer writes here)
