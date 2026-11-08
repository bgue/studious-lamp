# P2-I2-T06b — Five `n_a` readiness checks

Status: ready after S1 merged (staged)
Tier: haiku
Kind: ticket
Review: lite
Labels: core-module, readiness
Depends on: S1 (merged; `awp.IWP` exists as a record type); the readiness contract (on the trunk)
Branch: `p2/i2-t06b-na-checks`

## Goal
Five checks that the IWP engine finds by entry point and that answer `n_a` with a fixed note, so the names are reserved and the readiness screen lists them
(the modules they wait for do not exist yet). Each passes `check_readiness_contract` with `expect_n_a=True`.

## Brief references (pasted)
> Plan `08-phase2-plan.md` I2 T06b: checks `permits_planned`, `inspections_planned`, `labour_requested`, `predecessors_handed_over`, `model_slice_available`
> returning `n_a` with a fixed note, each with its test and name reserved. `n_a` counts as passing for readiness (README D9); it never blocks.
> All five: `version = "1"`, `watches = frozenset({"awp.IWP"})`, `state = "n_a"`, no `resolve_via`, `count_ok = count_total = None`, no connection use.

| name | fixed detail (exactly) |
|---|---|
| `permits_planned` | `not applicable yet: permit records are built in Phase 3` |
| `inspections_planned` | `not applicable yet: inspection and test plan records are built in Phase 3` |
| `labour_requested` | `not applicable yet: labour requisitions arrive with the requisitions module` |
| `predecessors_handed_over` | `not applicable yet: hand-over of predecessor work is not recorded` |
| `model_slice_available` | `not applicable yet: model records are built in Phase 3` |

## Interfaces (verbatim from repo)
```python
# tl_core.readiness
class ReadinessCheck(Protocol):
    name: str; version: str; watches: frozenset[str]   # watches: non-empty, record types that exist
    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult: ...
# IwpFacts: record_id, scope, key, status, planned_start, scope_ids: dict[str, list[str]], pinned_document_links: list[str] (link ids) ...
# CheckResult(name, version, state: "ok"|"blocked"|"pending"|"n_a"|"unknown", detail<=500, resolve_via: list[RecordRef] (<=50), count_ok, count_total)
# RecordRef(record_id, record_type, key)
```
Contract: read-only (no UoW, no write), never raises for a bad record (answers `unknown` with a fixed detail), detail is fixed text plus keys and counts (no path
separator other than `n/m`, no exception text, no titles). The entry point callable takes no argument and returns the check (see `materials_reserved` in
`packages/tl-modules/materials/src/tl_mod_materials/readiness.py` and its `pyproject.toml` table).
Entry points (new table in `packages/tl-modules/awp/pyproject.toml`, below the existing tables; one line per check, each callable returns the check):
```toml
[project.entry-points."throughline.readiness_checks"]
permits_planned = "tl_mod_awp.checks_na:permits_planned"
# ... the other four the same way
```
One small class `NotApplicable(name, detail)` in `checks_na.py` and five module-level zero-argument functions returning an instance.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/readiness/{types.py,harness.py}` and `dev/accept/P2-W0/W0-B1.py` (how `ContractWorld` and `load_checks` are used)
- `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (entry-point shape; the first 50 lines)
- `packages/tl-modules/awp/pyproject.toml`
may explore: (none)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` (create)
- `packages/tl-modules/awp/pyproject.toml` (the table above only)
- `dev/accept/P2-I2/T06b.py` (create), `docs/reports/P2-I2/T06b.md` (create)
- a pin that lists installed readiness checks, if one breaks (union form; list it in the report)
Not here: any other file of the package.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T06b.py
```
`T06b.py` (you write it; SQLite temp db made as `W0-B1.py` does, `record_types` includes `awp.IWP`; one `PASS <check>` per line, `FAIL <check>` and exit 1 otherwise):
`load_checks()` finds all five names; each has `version "1"` and `watches == {"awp.IWP"}`; `check_readiness_contract` passes for each with `expect_n_a=True`;
each answers exactly the detail in the table; the five names are distinct from `materials_reserved`; evaluating on a connection runs no statement (count with a
`before_cursor_execute` listener).

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T06b: ...`; the commit trailer is the attribution lines
your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Blocked
(implementer writes here)

## Escalation triggers
- Stop and report *Blocked* if `check_readiness_contract` rejects `watches == {"awp.IWP"}` (record type not found), or if the awp `pyproject.toml` has no place for the table.
- Note in the report: the plan gives `labour_requested` to I4-B T05 as a real check; that ticket must delete this entry (name collision is an error).
