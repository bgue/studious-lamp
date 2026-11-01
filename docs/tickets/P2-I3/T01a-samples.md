# P2-I3-T01a — Sample CSVs for the materials loaders

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs, fixtures
Depends on: —
Branch: `p2/i3-t01a-samples`

## Goal
Three data files that the loaders of T01b read and the demo loads: 50 library items, a five-level location tree and 12
PO lines. Data only, no code besides the acceptance script. (Split from spec ticket T01 so the data is ready before S2.)

## Brief references (pasted)
> Import targets: `materials.item_master` (company scope: code, description, category, uom, size, rating, material, consumable),
> `materials.location` (parents first), `materials.po_line`. Demo: 50-item library; locations project -> warehouse ->
> laydown L2 -> toolcrib -> gang box; a receipt of two flange lines, heat H-7781, against PO line 4471-3; a consumable issue needs a cost code.
> Item code `^[A-Z0-9][A-Z0-9._\-]{0,39}$`. Location code `^[A-Z0-9][A-Z0-9.\-]{0,15}$`, depth 0..5. PO number <= 30 chars,
> supplier text <= 120. Quantities: ASCII digits, > 0, at most 3 decimals, <= 1 000 000 000.
> Lists. category: `pipe fitting flange valve bolting structural plate cable instrument electrical insulation paint consumable concrete other`.
> uom: `EA SET BOX ROLL L m kg lb m3`. material (optional): `CS SS304 SS316L DUPLEX other`. location kind: `project warehouse laydown toolcrib gang_box`.

## Interfaces (the files and their exact header lines)
Directory `packages/tl-modules/materials/src/tl_mod_materials/samples/` (the package itself is S2's; create only this folder), UTF-8, LF, comma separated, no quoting unless a field holds a comma or a quote (then RFC 4180 quotes, `"` doubled).
- `items.csv`: `code,description,category,uom,size,rating,material,consumable`. `consumable` is `true` or `false`; `material` may be empty.
- `locations.csv`: `code,title,kind,parent_code`. Root has empty `parent_code`; a parent row precedes its children.
- `po_lines.csv`: `po_number,line_no,item_code,qty_ordered,uom,promised_date,supplier_text`. `promised_date` ISO.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/samples/{items,locations,po_lines}.csv` (create)
- `dev/accept/P2-I3/T01a.py` (create), `docs/reports/P2-I3/T01a.md` (create)

## Steps
1. `items.csv`: exactly 50 rows, unique codes, at least 8 categories used, at least 3 `consumable` rows (welding rod in `kg`, gloves or wire in `BOX`/`ROLL`; category `consumable`). Include `FLG-WN-6-150-A105` (description `Flange WN 6" 150# A105`, flange, EA, size `6"`, rating `150#`, CS, false) and a blind flange `FLG-BL-6-150-A105`; use realistic pipe, fitting, valve, bolting, structural, cable, instrument lines. `uom` fits the item (pipe `m`, plate `EA`, wire `ROLL`).
2. `locations.csv`: root `P123` (project), `WH1` warehouse under it, `L1` and `L2` laydown under `WH1`, `TC1` toolcrib under `L2`, `GB1` gang_box under `TC1`; add up to 4 more rows (never deeper than depth 4, never a second root).
3. `po_lines.csv`: at least 12 lines over POs `4471` and `4472`; `item_code` exists in `items.csv` and `uom` equals that item's `uom`; line `4471`/`3` is `FLG-WN-6-150-A105`, supplier `Acme Valves`; quantities like `20` or `12.500`.
4. `dev/accept/P2-I3/T01a.py` (stdlib `csv`, `re`, `datetime`; run from any directory; exit 0 and print `PASS <check>`; on a failure print `FAIL <check>` and exit 1) asserts every rule above: headers exact; 50 unique item codes matching the pattern; category, uom, material, kind values in the lists; `consumable` in true/false; at least 3 consumables and 8 categories; the demo flange row; each location code pattern, parent before child, exactly one root, the five kinds present at depths 0 to 4; PO lines at least 12, keys unique, item and uom agree, bounds, ISO dates, the 4471-3 row.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/T01a.py
just check
```
Expected: every line `PASS`, exit 0; `just check` clean (it lints the script; keep lines <= 100 characters, double quotes).

## Tests to add
None (tests deferred to T11, which writes `test_samples.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines. Deviations first. Do not discuss the commit attribution lines. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a list above is missing a value you need, or `just check` fails outside your files.

## Blocked
(implementer writes here)

## Decision
Round 2 (data done at 7ac62fc; blocked on the workspace). Q1: option (a). The package skeleton `pyproject.toml` is on `p2/i3`
at 2aef8fb; merge `p2/i3` into this branch first (no conflicts expected). Q2: `4471-4` accepted. Q3: depth 4 stands.
Remaining work: after the merge run `uv sync --all-packages`, then the Acceptance commands below with
`NODE_OPTIONS=--max-old-space-size=6144` exported (pyright), set the report Status to done, add the output. No data change.
