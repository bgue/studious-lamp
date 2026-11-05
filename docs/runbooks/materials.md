# Runbook — daily materials work: load, receive, stock, reserve, report

Purpose: load the item library and locations, receive and accept deliveries with their MTR, move, reserve and adjust stock, read the shortages and the movement log, and rebuild the stock projections. Brief: §2.1 (M4). Module: `packages/tl-modules/materials/README.md`.

## When to use
- Trigger: a new incumbent export arrives, a delivery arrives on site, a crew issues or returns material, a take-off line is short, or the stock figures look wrong after a restore.

## Before you start
- Access needed: `materials.view` for reads; `user` role for receive, move, reserve and assign; controller (or admin) for void, adjust, scrap, location edits and `tl load` on a company target. Run every command from the repository root with `uv run tl ...`.
- Set the ledger: pass `--db` or set `TL_DB` to the SQLite file or `postgresql://` URL. The CLI never prints the URL.
- Safe to run during business hours: yes for reads, receive, move and reserve. A load writes its new rows as one batch; run it when no one is posting to the same project.
- Every quantity is text (`--qty 2.5`) in the unit of the lot (`--uom`).

## Steps
1. See the installed loaders and their targets.
   ```
   uv run tl load loaders
   uv run tl load targets
   ```
   Expected: `mat-items`, `mat-locations`, `mat-po-lines`; `materials_item_master` is company scope, the other two are project scope.

2. Load the item library (company). Open the file, then read, check and load it.
   ```
   uv run tl load open items.xlsx --loader mat-items --company
   uv run tl load extract <run> --company
   uv run tl load profile <run> --company --show
   uv run tl load plan <run> --company
   uv run tl load load <run> --company --expect-new <N>
   ```
   Expected: `opened mat/items#<n> <id>`; `plan` prints the counts `new`, `existing` and `invalid`. Pass the `new` count you saw in the plan as `--expect-new`. Rows that exist are left alone.

3. Load locations and PO lines into a project (same pattern, project scope).
   ```
   uv run tl load open locations.csv --loader mat-locations --project P123
   uv run tl load open po.csv --loader mat-po-lines --project P123
   uv run tl load plan <run> --project P123
   uv run tl load load <run> --project P123 --expect-new <N>
   ```
   Expected: the same counts as step 2. To take a bad run back, `uv run tl load compensate <run> --project P123` ends the records it created.

4. Check the item library and the locations.
   ```
   uv run tl mat item --project P123
   uv run tl mat loc --project P123
   uv run tl mat po --project P123
   ```
   Expected: one line per item (`<code>  <category>  <base_uom>  projects <n>  ...`), then `locations: <n>` and the tree; `no items` or `no locations in project P123` when empty.

5. Receive a delivery. The receipt stays Received until it is inspected.
   ```
   uv run tl mat receipt receive --project P123 --location <location-code> --received-on 2026-11-05 --line <ITEM>:<QTY>:<HEAT> --po-line <po-line-key> --supplier "<supplier>" --delivery-ref <delivery-note>
   ```
   Expected: `received P123-RCPT-0001  <n> lines`. Give `--line` once per line, format `ITEM:QTY[:HEAT[:CONDITION]]`, 1 to 50 lines.

6. Attach the material test report (MTR) when the item category requires one. Required categories are listed in the project setting `materials.receipt.mtr_required_categories`.
   ```
   uv run tl file put mtr-P123-RCPT-0001.pdf --project P123 --record P123-RCPT-0001 --slot mtr
   ```
   Expected: the command prints the stored result. Accept is refused while a required MTR is missing.

7. Inspect the receipt, then accept or reject it. Accept creates one lot per line.
   ```
   uv run tl mat receipt inspect P123-RCPT-0001 --project P123 --notes "<what the inspection found>"
   uv run tl mat receipt accept P123-RCPT-0001 --project P123
   uv run tl mat receipt reject P123-RCPT-0001 --project P123 --reason "<why>"
   ```
   Expected: `P123-RCPT-0001 is Inspected`, then `... is Accepted` or `... is Rejected`. A rejected receipt makes no stock.

8. Read the receipts, and the open ones only when you need them.
   ```
   uv run tl mat receipt list --project P123
   uv run tl mat receipt list --project P123 --open
   uv run tl mat receipt list --project P123 --missing-mtr
   uv run tl mat receipt show P123-RCPT-0001 --project P123
   ```
   Expected: one line per receipt (`<number>  <state>  <received_on>  <location>  lines <n>  mtr <state>  <title>`), then the lines and files of `show`.

9. Void a receipt entered in error (controller; the reason is required).
   ```
   uv run tl mat receipt void P123-RCPT-0002 --project P123 --reason "entered twice"
   ```
   Expected: `P123-RCPT-0002 is Void`.

10. Read the stock.
    ```
    uv run tl mat stock --project P123
    uv run tl mat stock --project P123 --location <location-code> --subtree
    uv run tl mat lot P123-RCPT-0001@1 --project P123
    ```
    Expected: `stock rows: <n>`, then one line per lot and location with `on hand`, `reserved` and `available`; `lot` shows the heat, item, receipt, balances, reservations and the last ten moves.

11. Issue material to a work package or cost code. A consumable needs `--for-cost-code`.
    ```
    uv run tl mat move issue --project P123 --lot <lot-key> --qty 2 --uom EA --from <location-code> --for-cost-code <cost-code-id> --person "<who receives it>"
    ```
    Expected: `issue 2 EA lot <lot-key>`. The command refuses a quantity above what is available at the location.

12. Transfer between locations, or return stock to a location.
    ```
    uv run tl mat move transfer --project P123 --lot <lot-key> --qty 2 --uom EA --from <from-code> --to <to-code>
    uv run tl mat move return --project P123 --lot <lot-key> --qty 1 --uom EA --to <location-code>
    ```
    Expected: `transfer 2 EA lot <lot-key>`, `return 1 EA lot <lot-key>`.

13. Adjust a count (controller). Direction is required: `in` lands stock at `--to`, `out` takes it from `--from`. A reason is required.
    ```
    uv run tl mat move adjust --project P123 --lot <lot-key> --qty 1 --uom EA --direction in --to <location-code> --reason "cycle count"
    uv run tl mat move scrap --project P123 --lot <lot-key> --qty 1 --uom EA --from <location-code> --reason "damaged"
    ```
    Expected: `adjust 1 EA lot <lot-key>`, `scrap 1 EA lot <lot-key>`. Scrap is for damaged or nonconforming stock (controller).

14. Find the short take-off lines and assign lines to a work package.
    ```
    uv run tl mat mto list --project P123 --short-only
    uv run tl mat mto show ISO-1234@A/MTO/001 --project P123
    uv run tl mat mto assign ISO-1234@A/MTO/001 ISO-1234@A/MTO/002 --project P123 --work-package P123-IWP-0001
    ```
    Expected: `<key>  <item>  required <q>  reserved <q>  issued <q>  short <q>  for <wp>` per line; `assigned 2 lines to P123-IWP-0001`. Assign is refused for a line that has stock against it.

15. Reserve stock for a take-off line, and release a reservation. The `--for-line` value is the take-off line's record id. No read command prints that id yet (follow-up: `--for-line` should take the line key); until then read the `id` of the line from the API, `GET /projects/P123/materials/mto-lines`.
    ```
    uv run tl mat move reserve --project P123 --lot <lot-key> --qty 2 --uom EA --from <location-code> --for-line <line-record-id>
    uv run tl mat move unreserve --project P123 --lot <lot-key> --qty 2 --uom EA --from <location-code> --for-line <line-record-id>
    ```
    Expected: `reserve 2 EA lot <lot-key>`. A reservation above the available quantity is refused.

16. Read the shortages and the reports. Report names: `stock_on_hand`, `movement_log`, `mto_status`, `shortages`, `heat_trace` (needs `--heat`), `consumables_by_cost_code`.
    ```
    uv run tl mat report shortages --project P123
    uv run tl mat report stock_on_hand --project P123 --format csv
    uv run tl mat report heat_trace --project P123 --heat H-7781
    ```
    Expected: `table` format prints the columns, one line per row, then `rows: <n>`; `csv` prints the CSV verbatim. A bad name or date is `error: ...` on stderr, exit 1.

17. Read the movement log: all movements in ledger order, then by day.
    ```
    uv run tl mat movements --project P123
    uv run tl mat movements --project P123 --lot <lot-key> --since 2026-11-01 --until 2026-11-05 --kind issue
    uv run tl mat report movement_log --project P123 --since 2026-11-01 --until 2026-11-05
    ```
    Expected: `movements: <n>`, then `<date>  <kind>  <lot>  <item>  <+/-><q> <uom>  <from>  <to>  <actor>`. The sign is `+` for stock in and `-` for stock out.

18. Rebuild the stock projections from the ledger. Rebuild all of them, or one by name: `materials_item_master`, `materials_project_item`, `materials_location`, `materials_po_line`, `materials_lot`, `materials_receipt`, `materials_mto`, `materials_stock`.
    ```
    just rebuild-projections
    just rebuild-projections materials_stock
    ```
    Expected: the projectors are reset and the ledger is replayed into them. Run it after a restore, then repeat step 10 and compare.

## Verify
- `uv run tl mat stock --project P123` shows the figures you expected for the lot you moved.
- `uv run tl mat receipt show P123-RCPT-0001 --project P123` shows the receipt's state and its lines; `uv run tl mat lot <lot-key> --project P123` shows the lot the accept made.
- `uv run tl mat report stock_on_hand --project P123` lists the same balances as `tl mat stock`.

## Roll back
- Stock moves cannot be undone: the ledger is append-only. Post the opposite movement (a `return`, a `transfer` back, or an `adjust` with the other direction) with a reason.
- A receipt entered in error: `tl mat receipt void` (controller) before it is accepted, or after accept with a reason. A bad load: `tl load compensate <run> --project P123`, or `tl load void <run>` if nothing was loaded.
- A reservation made by mistake: step 15, `unreserve`.

## Related
- `packages/tl-modules/materials/README.md` (commands, screens, MCP tools, offline classes).
- `packages/tl-modules/materials/AGENTS.md` (package rules).
- `docs/runbooks/legacy-load.md` (the load steps in full).
- `docs/runbooks/rebuild-projections.md` (projection rebuild).
- `docs/build-spec/specs/m4-materials.md` (spec §3 commands and access words).
