# P2-I2-T06a1 — Readiness check `documents_current`

Status: ready after S1 and S2 merged (staged)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: S1, S2 (merged: pin command, `iwp_facts`); the readiness contract
Branch: `p2/i2-t06a1-documents-current`

## Goal
A read-only check `documents_current`, shipped by the documents module (awp may not import it), that answers whether every document pinned by an IWP is at
a current revision.

## Brief references (pasted)
> Plugin under `throughline.readiness_checks`, `version "1"`, `watches = frozenset({"documents.Document", "documents.Revision"})`. The IWP's pins are the links
> whose ids are in `iwp.pinned_document_links`. No pins -> `n_a` (`no documents pinned to this work package`). Each pin is resolved with
> `tl_mod_documents.resolver.links_to_documents(conn, iwp.scope)` (scope-wide, limit 1000), keeping the entries whose `link_id` is in `pinned_document_links`.
> Per pin: `resolution.state in ("current", "floating")` is current; `stale` is behind; `unknown` or `no_current` is not answerable. All current -> `ok`.
> Any `stale` or `no_current` or `unknown` -> `blocked`; `resolve_via`: the stale documents first (`RecordRef(document_id, "documents.Document", document_number)`),
> then the others, <= 50. `count_ok` / `count_total` = current pins / pins. Detail: `<ok>/<total> pinned drawings current` plus, when behind, `; <n> behind`. A failed
> read -> `unknown`, detail `the pinned documents of this work package could not be read`. At most 3 statements besides the resolver's own (count them in the acceptance).
> Reads without a viewer on purpose (a job runs it): keys and counts only, never titles.

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
`resolver.links_to_documents(conn, scope, *, document_id=None, only_stale=False, limit=1000) -> list[PinnedLink]`; `PinnedLink`: `link_id, document_id, document_number, pin, link_status, resolution`;
`PinResolution`: `state` in `current|stale|floating|no_current|unknown`, `newer_codes`. Entry point table, new, in `packages/tl-modules/documents/pyproject.toml`:
```toml
[project.entry-points."throughline.readiness_checks"]
documents_current = "tl_mod_documents.readiness:documents_current"
```
`links_to_documents` applies the viewer filter itself; confirm in the report that a job-run read (no viewer) sees the links, else answer `unknown` and say so (do not widen the filter).

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/readiness/{types.py,harness.py}`; `dev/accept/P2-W0/W0-B1.py`
- `packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (lines 60-225)
- `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (shape only)
- `packages/tl-modules/documents/pyproject.toml`; `packages/tl-modules/documents/tests/docworld.py` (how documents and revisions are made in a test world)
may explore: `dev/accept/P2-I3/S3.py` (a `World` class that builds a temp ledger)

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/readiness.py` (create)
- `packages/tl-modules/documents/pyproject.toml` (the table above only)
- `dev/accept/P2-I2/T06a1.py` (create), `docs/reports/P2-I2/T06a1.md` (create)
- a pin that lists installed readiness checks, if one breaks (union form; list it)
Not here: `resolver.py` and every other file of the package.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T06a1.py
```
`T06a1.py` (SQLite temp ledger; an IWP is a hand-made `awp.IWP` record with pin links written as the S2 pin command writes them, or by the command itself; one
`PASS <check>` per line): `load_checks()` finds `documents_current` with the stated `watches`; the contract passes for an IWP with no pins (`expect_n_a=True`) and
with pins; no pins -> `n_a`; two current pins -> `ok`, `2/2`; a new issued revision of one pinned drawing -> `blocked`, `1/2`, `resolve_via` is that document; a floating
pin -> counts as current; a pin on a revision that does not exist -> `blocked` (unknown resolution); a hidden pinned document does not change the answer shape (it
answers like a missing one); 60 stale pins -> `resolve_via` has 50 entries; statement count within the stated limit.

## Tests to add
None (S5 writes the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T06a1: ...`; the commit trailer is the attribution lines
your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Blocked
(implementer writes here)

## Escalation triggers
- Stop and report *Blocked* if `links_to_documents` cannot be called without a viewer, if `pinned_document_links` ids do not match `PinnedLink.link_id`, or if the contract rejects the shape.
