# P2-I2-T06a2 — Readiness check `rfis_answered`

Status: ready after S1 and S2 merged (staged)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: S1, S2 (merged); the readiness contract
Branch: `p2/i2-t06a2-rfis-answered`

## Goal
A read-only check `rfis_answered`, shipped by the correspondence module (awp may not import it), that answers whether every RFI linked from an IWP has an answer.

## Brief references (pasted)
> Plugin under `throughline.readiness_checks`, `version "1"`, `watches = frozenset({"correspondence.TechnicalItem"})`. The IWP's RFIs are the records of type
> `correspondence.TechnicalItem` (`names.TECHNICAL`) that the IWP has an active `references` link to (`cur_links.from_id = iwp.record_id`, `relation = 'references'`,
> `status = 'active'`, `to_id` = the item) and whose item row has `subtype = 'rfi'` (the item row is in `names.CORRESPONDENCE_TABLE`, joined to the Technical table
> `names.TECHNICAL_TABLE` on `id`; the subtype lives on the item row, not on the Technical table). Voided records and state `Void` are ignored. None -> `ok` with detail
> `no RFIs linked to this work package` (an IWP with no RFI is not blocked). State by workflow state (`cur_core_record.status`; NULL = Draft): `Answered`, `Accepted`, `Closed`
> are answered; `Issued`, `Awaiting response` are asked and open -> `pending`; `Draft`, `Internal review`, `Rejected` -> not asked or sent back -> `blocked`. Overall: any `blocked` ->
> `blocked`; else any `pending` -> `pending`; else `ok`. `resolve_via`: the blocked RFIs then the pending, `RecordRef(id, "correspondence.TechnicalItem", key)`, <= 50. `count_ok` /
> `count_total` = answered / RFIs. Detail: `<ok>/<total> RFIs answered`. A failed read -> `unknown`, detail `the RFIs of this work package could not be read`.
> One statement for the links and rows (a join), no per-RFI loop. Keys and counts only, never titles; reads without a viewer on purpose (a job runs it).

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
Entry point table, new, in `packages/tl-modules/correspondence/pyproject.toml`:
```toml
[project.entry-points."throughline.readiness_checks"]
rfis_answered = "tl_mod_correspondence.readiness:rfis_answered"
```
Workflow states of `correspondence.technical`: Draft, Internal review, Issued, Awaiting response, Answered, Accepted, Rejected, Closed, Void
(`schema/fixtures/workflows/correspondence-technical.yaml`).

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/readiness/{types.py,harness.py}`; `dev/accept/P2-W0/W0-B1.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py` (`TECHNICAL`, `TECHNICAL_TABLE`, workflow state names)
- `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (shape only)
- `packages/tl-modules/correspondence/pyproject.toml`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/views.py` or the Technical handler tests (find how a Technical item is created in a test world; one file)
may explore: `dev/accept/P2-I3/S3.py` (a `World` class that builds a temp ledger)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/readiness.py` (create)
- `packages/tl-modules/correspondence/pyproject.toml` (the table above only)
- `dev/accept/P2-I2/T06a2.py` (create), `docs/reports/P2-I2/T06a2.md` (create)
- a pin that lists installed readiness checks, if one breaks (union form; list it)
Not here: every other file of the package.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T06a2.py
```
`T06a2.py` (SQLite temp ledger; the IWP is a hand-made `awp.IWP` record; RFIs created by the correspondence commands or hand-written rows with `subtype = 'rfi'` on the item row; one `PASS <check>` per line):
`load_checks()` finds `rfis_answered`; the contract passes for the no-RFI world and a world with RFIs (this check never answers `n_a`, so `expect_n_a=False`); no RFI -> `ok`,
the fixed detail; all Answered/Accepted/Closed -> `ok`, `3/3`; one Awaiting response -> `pending`, `2/3`; a Draft one -> `blocked` wins over a pending one; a Void RFI is ignored; a TQ (subtype `tq`) linked is ignored; 60 open RFIs -> `resolve_via` has 50 entries; statement count at most 2 per evaluation.

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T06a2: ...`; the commit trailer is the attribution lines
your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Blocked
(implementer writes here)

## Escalation triggers
- Stop and report *Blocked* if the item row has no `subtype` holding `rfi`, if links from an IWP to an RFI cannot be read from `cur_links` as stated, or if the contract rejects the shape.
