# P2-WEB1-T17 — materials seed for the M4 twin tests

Status: staged (needs p2/i3 merged into p2/web1)
Tier: haiku
Kind: ticket
Review: lite
Labels: web, test
Depends on: p2/i3 merged into p2/web1 (`fakes_materials.py`, `tl_mod_materials.views`, `views_detail`)
Branch: `p2/web1-t17-materials-seed`

## Goal
`seed_materials(fake, project="P123")` fills a `FakeMaterialsSupport` (after `_init_materials()`) with a small consistent world, so the six M4 twin tests (T12 to T14b) share one data set, as `seed_awp` does for the M3 twins. Test support only; no product code.

## Pins
1. One new module `packages/tl-tui/tests/fakes_materials_seed.py` with `seed_materials(fake, project: str = "P123") -> None`. It imports only `tl_mod_materials.views` and `views_detail` (no sibling test module: the web tests load it by path). It calls `fake.put_materials(...)`, `put_material_items`, `put_mto_line_details`, `put_item_projects`.
2. The world (one story, ids and codes consistent across every list and detail):
   - 4 company items: 3 active, 1 retired (different categories and UOMs; `put_material_items`).
   - Locations: a root `WH`, children `WH-A` and `WH-B`, one grandchild `WH-A-1` (`depth`, `parent_code` right).
   - Stock: 4 rows over 3 lots: one lot in two locations, one lot with no heat, one lot whose lot key holds a `/`; quantities with three decimals; one row with reserved > 0.
   - Lot details for the 3 lots (reservations, last movements, `receipt` set for two of them, `None` for one).
   - Movements: 6, covering `receive issue transfer return adjust reserve`, both `direction` values and one `None`; two with a work package, one with a cost code, one with neither; ISO dates in 2026-10 and 2026-11; `seq` 1 to 6.
   - Receipts: 3 (one Received without MTR, one Inspected with MTR, one Accepted) with details (lines, delivery, inspection, files; one `mtr_required` with the MTR missing; the rejected case is not needed); one receipt's lot is the `/` lot.
   - Take-off lines: 3 (one short, one covered, one with no `need_by`), keys of the form `<doc>@<rev>/MTO-n`, with details (reservations, open receipts) via `put_mto_line_details`.
   - Item projects: for each item code a list of `ItemProjectView` (the first item in two projects, one item in none).
3. A test `packages/tl-web/tests/test_web_materials_seed.py` loads the fake and the seed by path (as `test_web_wbs_log.py` loads `fakes_awp.py`), seeds, and asserts: every list is non-empty except the one pinned empty; every `lot` of the stock rows has a lot detail; every receipt number has a detail; every MTO key has a detail; every `parent_code` is a code in the locations; the movements' `seq` are unique; each of the six list reads of the fake returns its rows.

## Context (read these, nothing else)
- `packages/tl-tui/tests/fakes_awp.py` (the model: `seed_awp`), `packages/tl-tui/tests/fakes_materials.py`
- `packages/tl-modules/materials/src/tl_mod_materials/views.py` (class definitions only), `views_detail.py`
- `packages/tl-web/tests/test_web_wbs_log.py` (the loader by path)
may explore: `docs/tickets/P2-I3/text-contracts.md`

## Allowed paths
- `packages/tl-tui/tests/fakes_materials_seed.py` (create)
- `packages/tl-web/tests/test_web_materials_seed.py` (create)
- `docs/reports/P2-WEB1/T17.md` (create)

## Acceptance
`uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`; `uv run pytest packages/tl-web/tests/test_web_materials_seed.py -q`. Paste the last 5 lines of each. Report at most 40 lines. Commit subject `P2-WEB1-T17: ...`, no model names.

## Escalation triggers
- *Blocked* if a view needs a field whose value cannot be made up without reading code outside the context list.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
