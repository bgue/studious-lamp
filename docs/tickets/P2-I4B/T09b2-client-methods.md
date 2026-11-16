# P2-I4B-T09b2 — Scaffold read methods on the clients and the fake

Status: staged (dispatch after T09b1 merges; read its report for the route names)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, confidentiality
Depends on: T09b1
Branch: `p2/i4b-t09b2-client-methods`
Worktree: `/home/user/wt/i4b/t09b2` (from `p2/i4b` head)

## Goal
Four read methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so the screens, the simulator and exports read scaffolds from any of them. Pattern: P2-PUNCH T04 (`docs/reports/P2-PUNCH/T04.md`; the punch methods are the model: `tl_api/client/quality.py`, the punch block of `embedded.py` and `client.py`, `tests/fakes_punch.py`). `RemoteClient` passes through.

## Interfaces (same names, parameters and errors on every implementation)
```python
def list_scaffolds(self, project, *, state=None, tag=None, overdue=False, limit=200) -> scaffold_views.ScaffoldPage
def get_scaffold(self, project, key) -> scaffold_views.ScaffoldDetail            # RecordNotFoundError (missing or hidden: one text, the route's constant)
def list_scaffolds_due(self, project, *, limit=200) -> list[scaffold_views.ScaffoldRow]
def export_scaffolds(self, project, *, fmt="csv", state=None, tag=None, overdue=False) -> str   # views.export_rows text; fmt csv|jsonl, else ValueError
```
Routes: T09b1 (`fmt` is the `format` query). Embedded: the same view calls the routes make, under the signed-in viewer (`current_viewer()`/the embedded client's viewer as the punch methods do), after the same `scaffold.view` word check, refusal as the punch methods refuse; never a second SQL path; `today` = `date.today().isoformat()`. Fake: answers from a list a test gives it (`load_scaffolds`, filters like the views, `total` before the limit, detail with inspections), `export_scaffolds` calls the real `views.export_rows`; `seed_scaffolds(client)` makes 5 scaffolds: Requested-state is not a row, so Designed, Erecting, Inspected green (due in the past), In Use green (due in the future), Modify red (failed inspection with 2 inspections), one hidden by key convention is not modelled.

## Context (read these, nothing else)
- `docs/reports/P2-I4B/T09b1.md`, `packages/tl-api/src/tl_api/routes/scaffold.py`, `packages/tl-modules/scaffold/src/tl_mod_scaffold/views.py` (dataclasses)
- `packages/tl-api/src/tl_api/client/quality.py`, `client/__init__.py` (mixin tuple), `packages/tl-tui/src/tl_tui/client.py` and `embedded.py` (the punch blocks), `packages/tl-tui/tests/fakes_punch.py` (all), `tests/fakes.py` (the punch mixin and `_init_punch()` lines)
- `tests/api/test_client_punch.py`, `packages/tl-tui/tests/test_fakes_punch.py` (the test shapes)

## Allowed paths
- `packages/tl-api/src/tl_api/client/scaffold.py` (create), `client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_scaffold.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and init lines)
- `tests/api/test_client_scaffold.py` (create), `packages/tl-tui/tests/test_fakes_scaffold.py` (create)
- consequential pins (rule 12, union form, listed): a client-method-list pin in `tests/api/test_client_roundtrip.py` or `packages/tl-tui/tests/test_remote_client.py` if the gate shows one
- `docs/reports/P2-I4B/T09b2.md` (create)

## Acceptance
```
uv sync --all-packages
just check
just gate tests/api/test_client_scaffold.py packages/tl-tui/tests/test_fakes_scaffold.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
```

## Tests to add
- `tests/api/test_client_scaffold.py`: ledger built by commands (scaffold `World` loaded by path, as `test_client_punch.py` loads its world; no projection writes except the hidden-scaffold one, only if a hidden case is added); the embedded client and `ApiClient` over a `TestClient` give equal answers for the four methods (rows, total, detail with inspections, due list, CSV and JSONL text equal); `RecordNotFoundError` with one text for a missing key on both; `export_scaffolds(fmt="xml")` raises `ValueError` on both.
- `packages/tl-tui/tests/test_fakes_scaffold.py`: `seed_scaffolds` counts, each filter narrows, `total` equals rows before the limit, the missing key raises `RecordNotFoundError`, the due list drops the future-due scaffold, the export text starts with the header line.

## Escalation triggers
- A T09b1 route lacks a field the screens need; the roundtrip test needs a change other than a method list; `ClientInterface` already holds one of the names.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4B-T09b2: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
