# P2-I3-T01b — Loaders mat-items, mat-locations, mat-po-lines

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: loaders
Depends on: S2 (merged), T01a (merged: the three sample CSVs are in the package)
Branch: `p2/i3-t01b-loaders`

## Goal
Three loaders that `tl load loaders` lists and that load the T01a sample files through the S2 load targets. A loader is a
`LoaderDef` returned by a function named in the `throughline.loaders` entry-point group (the form of
`packages/tl-modules/legacy/src/tl_mod_legacy/loaders/instrument_index.py`). The targets are hand-written (S2) and read grid columns by
name, so each loader's mapping text is a plain YAML description of the columns and is only hashed by the framework.

## Brief references (pasted)
> Loaders `mat-items`, `mat-locations`, `mat-po-lines` (spec §5); targets `materials_item_master` (company scope: code, description, category,
> uom, size, rating, material, consumable), `materials_location` (parents first: code, title, kind, parent_code), `materials_po_line`
> (po_number, line_no, item_code, qty_ordered, uom, promised_date, supplier_text). `tl load` stays admin.
> `LoaderDef(name, system, table, target, description, mapping_text, file_types=("csv","xlsx"), sheet=None, header_row=1, confidentiality=None)`;
> `system` and `table` match `[a-z][a-z0-9_]{0,30}`; `target` is the target's registered (entry point) name.

## Interfaces (verbatim from repo)
```python
# tl_mod_legacy.model
@dataclass(frozen=True)
class LoaderDef:
    name: str; system: str; table: str; target: str; description: str; mapping_text: str
    file_types: tuple[str, ...] = ("csv", "xlsx"); sheet: str | None = None
    header_row: int = 1; confidentiality: str | None = None
```
Entry points to add to `packages/tl-modules/materials/pyproject.toml`, as a new table directly below the `throughline.load_targets` table:
```toml
[project.entry-points."throughline.loaders"]
mat-items = "tl_mod_materials.loaders.materials:items_loader"
mat-locations = "tl_mod_materials.loaders.materials:locations_loader"
mat-po-lines = "tl_mod_materials.loaders.materials:po_lines_loader"
```
Loader values: `mat-items` system `mat` table `items` target `materials_item_master`; `mat-locations` system `mat` table `locations` target
`materials_location`; `mat-po-lines` system `mat` table `po_lines` target `materials_po_line`. `file_types` `("csv", "xlsx")`.
`mapping_text`: a module constant per loader, YAML text with keys `name`, `description`, `delimiter: ","`, `columns:` (a list of the column
names the target reads, in the file's order, as in the sample header).

## Context (read these, nothing else)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/instrument_index.py` and `packages/tl-modules/legacy/src/tl_mod_legacy/model.py` (`LoaderDef`)
- `packages/tl-modules/materials/pyproject.toml`
- `packages/tl-modules/materials/src/tl_mod_materials/samples/{items,locations,po_lines}.csv` (headers only)
- `packages/tl-modules/legacy/src/tl_mod_legacy/testing.py` (`LegacyWorld`, `ADMIN`, `PROJECT`; the form for the acceptance script)
may explore: `dev/accept/P2-I3/S2.py` (how a target is planned and applied on a temp ledger)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/loaders/__init__.py`, `loaders/materials.py` (create)
- `packages/tl-modules/materials/pyproject.toml` (the table above only)
- `dev/accept/P2-I3/T01b.py` (create), `docs/reports/P2-I3/T01b.md` (create)
- a pin that lists the installed loaders, if one breaks (list it in the report)

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run tl load loaders
uv run python dev/accept/P2-I3/T01b.py
just check
```
Expected: `tl load loaders` lists `mat-items`, `mat-locations`, `mat-po-lines`. `T01b.py` (you write it; stdlib plus the repo, a temp SQLite ledger via
`LegacyWorld`; exit 0, one `PASS <check>` line each; `FAIL <check>` and exit 1 otherwise) asserts: the three loaders are found by `load_loaders()`
with the target names above; run 1, company scope, `mat-items` with `items.csv` (`open`, `extract`, `profile`, `bronze`, `plan`) reports 50 new and
`load` creates 50 `materials.ItemMaster` records, `reconcile` 0 mismatches; a second run of the same file plans 0 new and 50 existing; run 2, project
scope, `mat-locations` with `locations.csv` loads 9; run 3, project scope, `mat-po-lines` with `po_lines.csv` loads 15; opening `mat-items` with a
project scope is refused. Use the service method names of `tl_mod_legacy/service.py`; the stages and their order are in `tl_cli/load.py`.

## Tests to add
None (T11 writes `test_loaders.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Do not discuss the commit attribution lines. No model names in any
committed file. Commit subjects `P2-I3-T01b: ...`.

## Escalation triggers
- Stop and report *Blocked* if a plan reports a problem for a sample row (the sample or a target is wrong: name the row number and the problem, do not edit
  the samples or `targets.py`), or `LoaderDef` rejects a value above.

## Blocked
(implementer writes here)
