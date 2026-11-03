# P2-I3-S3 — Receipts, movements, actions, commands, API glue

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core-module
Depends on: S2 (merged, af76b84 + e543b97); S1 (merged)
Branch: `p2/i3-s3-receipts`

## Goal
After this piece stock enters through an accepted receipt and moves through checked movements: the receipt workflow
(create, revise, inspect, accept, reject, void), the eight movement kinds behind `post_movements`, the `RULES` table
that drives offers, the module's command table complete (the draft stopgap gone), `propose_reservation`, the read views
T04a and T05 need, and the `tl_api` glue that turns the two red pins green. S2 already projects every event; this piece
only appends events, after reading projection rows inside the unit of work.

## Brief references
`docs/build-spec/specs/m4-materials.md` §2 (Movements are events; Receipt workflow; Rules; Links), §3 (rows of
CreateReceipt..ScrapStock; `post_movements`; generic allow-list), §5 (views you add), §6 (the whole table), §9 row S3.
`docs/adr/0022-inventory-movements-as-events.md`. S2 report `docs/reports/P2-I3/S2.md` (deviations 3-5: `from_location_id`
on reserve/unreserve/issue/scrap/adjust-out, `to_location_id` on receive/return/adjust-in; the projector raises on a
negative balance as a last line; quantities `Decimal`, never SQL arithmetic). Projection semantics: S2 spec "Projection
semantics S3/S4 rely on" (`docs/tickets/P2-I3/S2-package.md`).

**Decisions (orchestrator, 2026-11-01; they override the spec where they differ)**
1. *Glue is yours* (F4 of the S2 review): `tl_api/commands.py` gets `*_module_specs("materials", MATERIALS_COMMANDS)` (import
   beside `COST_COMMANDS`); `tests/services/test_module_role_seams.py` gets `"materials": MATERIALS_COMMANDS` in
   `API_COMMANDS_OF`; `tl_api/errors.py` gets one row per class of `tl_mod_materials/errors.py` (`from tl_mod_materials import
   errors as mat`; codes `materials_*`, unique; not-found 404, in-use and state 409, the rest 422), **including the four MTO
   classes the supervisor already added** (`MtoPublishRefusedError`, `MtoLineNotFoundError`, `MtoLineInUseError`,
   `WorkPackageNotFoundError`) and any you add; `openapi.json` regenerated (`uv run python -m tl_api.openapi`, see `--help`).
   S4 adds `AssignMtoLines` beside you; the orchestrator regenerates `openapi.json` once more at merge.
2. *Target names* are underscore (`materials_item_master` ...); load targets stay hand-written (F1).
3. *Stopgap out.* Delete `DRAFT_COMMAND_WORDS` from `commands.py`; `module.py` takes `command_words` from `MATERIALS_COMMANDS`
   only (`IssueStock`, `TransferStock`, `ReturnStock` are now real rows). `offline_drafts` stays.
4. *You own* `errors.py` (append), `commands.py`, `module.py`, `views.py`, `guards.py`; S4 owns `mto.py`, `handlers/mto.py` and
   the package `pyproject.toml`. Do not touch those three. `MTO_COMMANDS` / `MTO_RULES` are splatted by you, never edited.
5. *Seed ledger.* `dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db` leaves a SQLite ledger (add `.accept/` to `.gitignore`):
   the 50 sample items loaded through the `materials_item_master` target, the five-level tree, PO line `4471-3` and the other sample
   PO lines, one accepted receipt of two flange lines heat `H-7781` at `L2` (two lots), and an MTO of 3 lines for work package
   `P123-CWP-PIP-0001` written by hand-appended `MTO.Defined` / `MTOLine.Defined` events (S4 adds the real publish path). Company
   superuser and a plain user are different actors in the script.
6. *Reads you add to `views.py`* (viewer-filtered like S2's): `receipts`, `receipt_detail`, `mto_lines(conn, scope, *, work_package=,
   short_only=)`, `reservations_for_iwp(conn, iwp_id)`, `mto_lines_for(conn, record_id)`. T04a, T05, T07 import them.

## Interfaces (keep these names)
- `handlers/receipts.py`: `CreateReceipt`, `ReviseReceipt`, `InspectReceipt`, `AcceptReceipt`, `RejectReceipt`, `VoidReceipt` + handlers
  (payloads of spec §3). Accept: one unit of work as spec §2 *Accept* (lots, `Moved` receive, `Receipt.Accepted`, `Workflow.Transitioned`),
  MTR rule via the project setting `materials.receipt.mtr_required_categories`; `expected_version` checked. A Void after Accepted is
  refused (spec: Void is Received/Inspected only). `RejectReceipt` is `materials.receipt.decide` (user) per Q3 default.
- `handlers/movements.py` and `api.py`: `post_movements(uow, movements, *, actor, source, by_module=False)` (public surface, contracts
  §4) and the seven commands `IssueStock`, `TransferStock`, `ReturnStock`, `ReserveStock`, `UnreserveStock`, `AdjustStock`, `ScrapStock`, each
  `{movements: list[Movement] (1..200)}`; `Movement` fields as the `cur_materials_movement` columns (`lot_key`, `qty` text, `uom`, `from`/`to`
  location codes, `cost_code_id`, `mto_line_id`, `reason`, `person`, `direction` for adjust). All or nothing; every rule of spec §2 *Movements*;
  zero, negative, non-ASCII digit, 4 decimals and over 1e9 quantities refused with the fixed `InvalidQuantityError` message; `uom` must equal
  the lot's; no negative balance anywhere (adjust included); checks read projection rows inside the append's unit of work (the ledger
  writer lock serialises two concurrent issues: the second sees the first). Events `feed_policy: none`.
- `actions.py`: `RULES` (spec §6 verbatim, one row per line of the table) plus `*MTO_RULES`; `offers(...)` function with the shape of
  `tl_mod_cost`/`tl_mod_schedule` actions modules; agents are offered nothing; every row's word equals the command's access word.
- `commands.py`: `MATERIALS_COMMANDS` complete = S2's nine + receipts (6) + movements (7) + `*MTO_COMMANDS`. Words: `materials.receive`
  (Create/Revise/Inspect), `materials.receipt.decide` (Accept/Reject), `materials.void`, `materials.move` (Issue/Transfer/Return),
  `materials.reserve` (Reserve/Unreserve), `materials.adjust` (Adjust/Scrap); all exist in `schema/settings/access-words.yaml`.
- `module.py`: `proposable=(ProposableCommand(propose_reservation -> ReserveStock),)` per `tl_core/modules.py:ProposableCommand`
  (see `tl_mod_schedule/module.py` for the form); accepting person needs `materials.reserve`.
- Links (spec §2): Receipt `references` its PO line; StockLot `derived_from` its receipt; module-written.

## Context (<= 10 files)
- the Brief references; `packages/tl-modules/materials/src/tl_mod_materials/{common.py,registry.py,module.py,commands.py,guards.py,
  projectors/stock.py,projectors/receipts.py,handlers/po_lines.py}` (form of a handler)
- `schema/modules/materials/{events.yaml,receipt.yaml,movement.yaml}`; `schema/fixtures/workflows/materials-receipt.yaml`
- `packages/tl-modules/schedule/src/tl_mod_schedule/{module.py,actions.py}` (proposable and actions form)
may explore: `dev/accept/P2-I3/S2.py` (ledger setup and replay form), `packages/tl-core/src/tl_core/numbering` (allocator)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/{commands,module,views,errors,guards,actions,api}.py`,
  `handlers/{receipts,movements}.py` (create), `projectors/**` only for a defect found (list it in the report)
- `packages/tl-api/src/tl_api/{commands,errors}.py` (glue lines only), `packages/tl-api/openapi.json` (regenerated)
- consequential pins: `tests/services/test_module_role_seams.py` (the `API_COMMANDS_OF` line), others that enumerate commands, listed in the report
- `.gitignore` (one line `.accept/`), `dev/accept/P2-I3/S3.py` (create), `docs/reports/P2-I3/S3.md` (create)
Not here: `mto.py`, `handlers/mto.py`, the package `pyproject.toml`, `schema/**`, `generated/**`, API read routes (T04a), CLI, TUI, MCP.

## Acceptance (run once; no pytest; tests are T11's)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just gate tests/services packages/tl-api/tests/test_error_table.py packages/tl-modules/materials packages/tl-core/tests/test_offline_capture.py
```
`S3.py` (SQLite, then `TL_PG_URL` when set; exit 0; one `PASS <check>` each; written from spec §2/§3/§6, not from your code):
create/revise/inspect/accept with the two-line flange receipt (two lots at `L2`, `po_line.qty_received` up); Accept without the MTR when category `flange` is required (set the project setting in the script) is refused with `an MTR is required for <n> lines; attach it in the MTR slot`; RCPT numbers gap-free; Void refused
after Accepted; issue (consumable without cost code refused, over-issue refused, reservation consumed first), transfer (`from = to`
refused, inactive location refused), return above `issued_net` refused, adjust/scrap need a reason and a superuser (a user refused with
the word's message), reserve (over `available`, over the line qty, wrong item refused), unreserve over reserved refused; every refusal
leaves the ledger unchanged (event count equal); a batch of 201 refused; a batch with one bad row writes nothing; non-ASCII digit, `-1`,
`0`, `1.2345`, `1000000000.001` refused; rebuild-projections gives identical stock, reservation and movement rows; **two concurrent
issues of the last 5.000 (two processes or threads, `TL_PG_URL`): exactly one succeeds**; `offers()` lists the right commands per state
and role and nothing for an agent; `propose_reservation` by an agent produces a proposal, not an event; hidden-record read returns nothing.

## Tests to add
None (deferred to T11: `test_receipts.py`, `test_movements.py`, `test_actions.py`, `test_api_surface.py`).

## Mutation guards (sentinel + at most 5; report in 3 lines, `file:line` each, for T11)
MTR guard removed; negative-balance check (`<` to `<=` or removed); reserve total over the line qty; consumable cost-code requirement; word of
a row swapped (`materials.adjust` to `materials.move`). Run on `S3.py`.

## Report requirements
Piece report (<= 60 lines): deviations first; pins changed; acceptance output (<= 5 lines per command); builder return <= 15 lines in Code 92.
Do not discuss the commit attribution lines. No model names in any committed file. Commit subjects `P2-I3-S3: ...`.

## Escalation triggers
Stop and write *Blocked* if: a projector defect needs more than a few lines; the ledger writer lock cannot serialise two issues (a `tl_core`
change); a word a command needs is missing from `access-words.yaml`; the proposable form needs a `tl_core` change; a pin outside the listed kinds breaks.

## Blocked
(builder writes here)
