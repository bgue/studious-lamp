# P2-I4A-T04c2 — Requisition and work order read methods on the clients and the fake

Status: staged (dispatch after T04c1 merges; read its report for the route model names)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, confidentiality
Depends on: T04c1
Branch: `p2/i4a-t04c2-client-methods`
Worktree: harness-created under `/home/user/wt/i4a/t04c2` (from `p2/i4a` head)

## Goal
Four read methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so screens and tools read requisitions and work orders from any of them. Pattern: `docs/tickets/P2-I2/T04c2-client-methods.md` (the IWP methods are the model: `tl_api/client/iwp.py`, `embedded.py`, `tests/fakes_iwp.py`). `RemoteClient` passes through.

## Interfaces (same names, parameters and errors on every implementation)
```python
def list_requisitions(self, project, *, kind=None, state=None, requester=None, for_key=None, limit=200) -> <list model: rows, total>
def get_requisition(self, project, key) -> <detail model>          # RecordNotFoundError (missing or hidden: one text)
def list_work_orders(self, project, *, state=None, assigned_to=None, limit=200) -> <list model: rows, total>
def get_work_order(self, project, key) -> <detail model>           # RecordNotFoundError
```
Routes: T04c1 (`for_key` is the `for` query). Embedded: the same calls the routes make, under the signed-in viewer, after the same `requisitions.view` check (a refusal is the module's refusal error); never a second SQL path. Fake: answers from lists a test gives it (`load_requisitions`, `load_work_orders`), filters like the views; `seed_requisitions(client)` makes 5 requisitions (two labour, one material, one general, one scaffold; one Approved with a Scheduled work order, one Rejected) and 2 work orders.

## Context (read these, nothing else)
- `docs/reports/P2-I4A/T04c1.md`, `packages/tl-api/src/tl_api/routes/requisitions.py`
- `packages/tl-api/src/tl_api/client/iwp.py`, `client/__init__.py` (mixin tuple), `packages/tl-tui/src/tl_tui/client.py` (the IWP block), `embedded.py` (the IWP block)
- `packages/tl-tui/tests/fakes_iwp.py` (all), `tests/fakes.py` (mixin and `_init_iwp()` lines)

## Allowed paths
- `packages/tl-api/src/tl_api/client/requisitions.py` (create), `client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_requisitions.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and init lines)
- `tests/api/test_client_requisitions.py` (create), `packages/tl-tui/tests/test_fakes_requisitions.py` (create)
- `docs/reports/P2-I4A/T04c2.md` (create)

## Acceptance
```
uv sync --all-packages
just check
just gate tests/api/test_client_requisitions.py packages/tl-tui/tests/test_fakes_requisitions.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
```

## Tests to add
- `tests/api/test_client_requisitions.py`: ledger built by commands (module `req_world.py` helper loaded by path; no projection writes); embedded client and `ApiClient` over a `TestClient` give equal answers for the four methods; `RecordNotFoundError` with one text for a missing key on both; an actor without `requisitions.view` is refused by the embedded list.
- `packages/tl-tui/tests/test_fakes_requisitions.py`: `seed_requisitions` counts, each filter narrows, `total` equals rows, missing key raises `RecordNotFoundError`.

## Escalation triggers
- A T04c1 model lacks a field the screens need; the roundtrip test needs a change other than a method list; `ClientInterface` already holds one of the names.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4A-T04c2: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
