# P2-I3-T03 — Readiness check `materials_reserved`

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: S2, S3 (merged); W0-B1 readiness contract (on the trunk)
Branch: `p2/i3-t03-readiness`

## Goal
A read-only readiness check `materials_reserved` that the IWP engine finds by entry point: it answers, for one IWP, whether its material
take-off lines are covered by reservations and issues. It passes `check_readiness_contract`.

## Brief references (pasted)
> Plugin under `throughline.readiness_checks`, `version "1"`, `watches = {materials.StockLot, materials.MTOLine, materials.Receipt}`. Lines = MTO lines whose
> `work_package_id` is the IWP. None -> `n_a` (`no material take-off lines on this work package`). A line is covered when `reserved_qty + issued_qty >= qty`.
> All covered -> `ok`. Otherwise `pending` when every short line's item has an open receipt (Received or Inspected) or a PO line promised on or before
> `planned_start`, else `blocked`. `resolve_via`: short lines first, then those open receipts, <= 50; `count_ok` / `count_total` = covered / lines. One query
> per kind of row, no per-line loop.
> Contract (`tl_core/readiness/types.py`): a check is read-only (no UoW, no write), never raises for a bad record (answers `unknown` with fixed text), `detail`
> <= 500 characters, fixed text plus keys and counts only (no path separator other than `n/m`, no exception text), `resolve_via` <= 50 `RecordRef(record_id, record_type, key)`.

## Interfaces (verbatim from repo)
```python
# tl_core.readiness
class ReadinessCheck(Protocol):
    name: str; version: str; watches: frozenset[str]
    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult: ...
# IwpFacts: record_id, scope, key, status, planned_start: date | None, ...
# CheckResult(name, version, state: "ok"|"blocked"|"pending"|"n_a"|"unknown", detail, resolve_via: list[RecordRef], count_ok, count_total)
```
Entry point (new table in the package `pyproject.toml`, below the existing tables; the callable takes no argument and returns the check):
```toml
[project.entry-points."throughline.readiness_checks"]
materials_reserved = "tl_mod_materials.readiness:materials_reserved"
```
Tables: import the names `MTO_LINE_TABLE`, `RECEIPT_TABLE`, `RECEIPT_LINE_TABLE`, `PO_LINE_TABLE`, `PROJECT_ITEM_TABLE` from `tl_mod_materials.names` (as `views.py` does);
`views.mto_lines_for` and `views._receipt_state` show the columns and the state rule (`status` NULL = Received; `voided` rows are not open). Quantities are
read as `Decimal(str(x))` (`common.dec`); no SQL arithmetic on quantities (SQLite returns NUMERIC as float). The check reads without a viewer on purpose (a job
runs it); its detail and `resolve_via` carry keys and counts only, never titles.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/readiness/{types.py,harness.py}` and `dev/accept/P2-W0/W0-B1.py` (how a check and `ContractWorld` are built)
- `packages/tl-modules/materials/src/tl_mod_materials/{views.py,names.py,common.py}` (`mto_lines_for`, `_LINE_SELECT`, receipt and PO-line columns)
- `packages/tl-modules/materials/pyproject.toml`
- `dev/accept/P2-I3/S3.py` (the `World` class: a temp ledger, commands, rows; `--keep` writes `.accept/p2-i3.db`)
may explore: `schema/modules/materials/{mto,receipt,po_line}.yaml`

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (create)
- `packages/tl-modules/materials/pyproject.toml` (the table above only)
- `dev/accept/P2-I3/T03.py` (create), `docs/reports/P2-I3/T03.md` (create)
- a pin that lists installed readiness checks, if one breaks (list it in the report)
Not here: `views.py` and every other file of the package.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/T03.py
```
`T03.py` (you write it; SQLite temp ledger built with the `World` helper of `S3.py` by importing it with `sys.path`, or the same calls copied; exit 0, one
`PASS <check>` line each, `FAIL <check>` and exit 1 otherwise), each check from the brief above, not from your code: `load_checks()` finds
`materials_reserved` with `watches` as above; `check_readiness_contract(load_checks()["materials_reserved"], ContractWorld(...))` passes for a work package with
no lines (`expect_n_a=True`) and for one with lines; no lines -> `n_a` with the fixed detail; all lines covered (reserve through `post_movements`) -> `ok`,
`count_ok == count_total`; a short line whose item has a Received receipt -> `pending` and `resolve_via` lists the short line then the receipt; a short
line with no receipt and a PO line promised after `planned_start` -> `blocked`, `resolve_via` names the line; a PO line promised on or before `planned_start`
-> `pending`; an issued quantity counts as covered; a voided receipt does not make a line `pending`; 60 short lines -> `resolve_via` has 50 entries; the
statements run for one evaluation are at most 6 (count them with a `before_cursor_execute` listener). IWP identity: a hand-made `awp.IWP` record or the id of
the seed's CWP is enough, the check only compares `work_package_id` to `iwp.record_id`.

## Tests to add
None (T11 writes `test_materials_reserved.py`).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I3-T03: ...`; the commit trailer is the attribution lines
your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any
committed file.

## Escalation triggers
- Stop and report *Blocked* if a column the brief needs is not in the tables (name it), if `check_readiness_contract` rejects the shape the brief gives, or if the
  statement count cannot stay at 6 without changing `views.py`.

## Blocked
(implementer writes here)
