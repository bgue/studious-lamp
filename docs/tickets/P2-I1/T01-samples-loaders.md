# P2-I1-T01 — Samples, mappings and loaders `awp-wbs`, `awp-cwa`

Status: ready
Tier: haiku
Review: lite
Labels: core
Depends on: T02 (merged @518f6a1)
Branch: `p2/i1-t01-loaders`
Worktree: `/home/user/wt/i1-t01` (from `p2/i1` head)

## Goal
`tl load loaders` lists `awp-wbs` and `awp-cwa`; two sample CSV files ship with the awp package and load through the T02
targets (`awp_wbs`, `awp_cwa`). The sample WBS file has 12 valid nodes and one row whose percentages sum to 101.

## Brief references (pasted; spec §6)
Loaders `awp-wbs` and `awp-cwa` (CSV and XLSX, sample mapping files) are entry points of the awp package. The target reads
the grid by column name, lower-cased and trimmed: WBS `code`, `title`, `parent`, `cost_codes` (`CODE:PCT;CODE:PCT`); CWA
`code`, `title`, optional `sequence`. The loader's `mapping_text` is only hashed for these targets (no import mapping is read).
Acceptance of the spec: `tl load open/extract/plan` on `wbs-sample.csv` reports 12 new, 1 invalid (runbook `legacy-load.md`).

## Interfaces (verbatim)
```python
# tl_mod_legacy/loaders/equipment_list.py (shape to copy)
def loader() -> LoaderDef:
    return LoaderDef(name="equipment-list", system="equip", table="list", target="tags", description="...",
        mapping_text=read_mapping("equipment-list.yaml"), file_types=("xlsx",), sheet="Equipment List", header_row=3)
# LoaderDef(name, system, table, target, description, mapping_text, file_types=("csv","xlsx"), sheet=None, header_row=1)
# tl_mod_legacy/loaders/__init__.py: read_mapping(filename) reads files(__package__)/"mappings"/filename
# pyproject: [project.entry-points."throughline.loaders"]  equipment-list = "tl_mod_legacy.loaders.equipment_list:loader"
```
Sample WBS (13 rows, parents first): 12 valid nodes (roots `1`, `2`; `1.1`, `1.2`, `2.1`, leaf `2.2`; leaves `1.1.1`, `1.1.2`,
`1.2.1`, `1.2.2`, `2.1.1`, `2.1.2`) and one invalid leaf `2.1.3` with `cost_codes` `WLD:50;ERC:51` (sums to 101). Cost codes on
the valid leaves: `WLD:60;ERC:40` or `TST:100`, or none.
Sample CWA: 4 rows, `sequence` 1..4 (`CWA-A`..`CWA-D`).

## Context (read these, nothing else)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/equipment_list.py` and `.../loaders/__init__.py`
- `packages/tl-modules/awp/pyproject.toml`, `packages/tl-modules/awp/src/tl_mod_awp/targets.py` (lines 85-110 only: column names)
- `docs/runbooks/legacy-load.md` (steps 1-4)
may explore: (none)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/loaders/__init__.py`, `awp.py`, `mappings/awp-wbs.yaml`, `mappings/awp-cwa.yaml` (create)
- `packages/tl-modules/awp/src/tl_mod_awp/samples/wbs-sample.csv`, `cwa-sample.csv` (create)
- `packages/tl-modules/awp/pyproject.toml` (the two entry-point lines only), `uv.lock` (if `uv sync` rewrites it)
- `dev/accept/P2-I1/T01.py`, `docs/reports/P2-I1/T01.md` (create)

## Steps
1. `loaders/__init__.py` gets `read_mapping` (copy, package `tl_mod_awp.loaders`). `awp.py` has `wbs_loader()` and `cwa_loader()`
   (`system="awp"`, `table` `wbs` / `cwa`, `target="awp_wbs"` / `"awp_cwa"`, `file_types=("csv","xlsx")`).
2. Mapping files: a YAML comment header naming the columns above and `name:` only; no secrets, no cell text.
3. pyproject: `awp-wbs = "tl_mod_awp.loaders.awp:wbs_loader"` and `awp-cwa = ...:cwa_loader` under `throughline.loaders`.
   Run `uv sync --all-packages` after.
4. `T01.py`: in a scratch ledger (copy the opening of `dev/accept/P2-I1/T02.py`: schema, admin account, cost codes
   `WLD ERC TST`) run `tl load open/extract/plan` on `wbs-sample.csv`; print `PASS plan new 12 invalid 1`, and `PASS loaders
   listed`; the CWA sample plans 4 new and the path. Ends `T01 ok`. No pytest.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/T01.py
uv run tl load loaders
```
Expected: `just check` clean; `T01 ok`; `awp-wbs` and `awp-cwa` listed with targets `awp_wbs`, `awp_cwa`.
If the plan counts differ from `12 new, 1 invalid`, write *Blocked*; do not edit `targets.py`.

## Tests to add
none (T11 writes `test_loaders.py`, `test_fixtures.py`).

## Report requirements
`docs/reports/P2-I1/T01.md` <= 60 lines. Subject `P2-I1-T01: ...`; no model names.

## Escalation triggers
- Stop if a file outside Allowed paths must change, or the target refuses the sample for a reason not in this ticket.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
