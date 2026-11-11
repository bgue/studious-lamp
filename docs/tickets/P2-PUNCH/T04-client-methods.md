# P2-PUNCH-T04 — Punch read methods, the `quality_command` door and the fake

Status: staged (dispatch after T03 merges; the route model names are in its report)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, access
Depends on: T03
Branch: `p2/punch-t04-client`
Worktree: harness-created under `/home/user/wt/punch/t04` (from `p2/punch` head)

## Goal
Three read methods and one write door exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so screens and tools read punch items and run punch commands from any of them. Pattern: `docs/tickets/P2-I4A/T04c2-client-methods.md` and the materials client (`tl_api/client/materials.py` and its `materials_command`, `embedded.py` `_module_command(name, cmd, COMMANDS, "module")`). `RemoteClient` passes through.

## Interfaces (same names, parameters and errors on every implementation)
```python
def list_punch_items(self, project, *, state=None, area=None, system=None, assignee=None, category=None, from_key=None, overdue=False, limit=200) -> PunchPage
def get_punch_item(self, project, key) -> PunchDetail            # RecordNotFoundError (missing or hidden: one text)
def get_punch_counts(self, project) -> dict[str, int]
def quality_command(self, name, cmd) -> CommandResult            # name is a model of PUNCH_COMMANDS, run as the person
```
Routes: T03 (`from_key` is the `from` query). Embedded: the same calls the routes make, under the signed-in viewer, after the same `quality.view` check (a refusal is the module's refusal error); never a second SQL path; a command names the item by `punch_item` = `PunchRow.id`; `quality_command` goes through `_module_command` with `PUNCH_COMMANDS`. `ApiClient.quality_command` posts to `/commands/<name>`. Fake: answers from lists a test gives it (`load_punch`), filters like the views, records each command in `sent_commands`-style list as the materials fake does; `seed_punch(client)` makes 6 items (two Open, one Cleared, one Verified, one Void, one from a source key), one overdue.

## Context (read these, nothing else)
- `docs/reports/P2-PUNCH/T03.md`, `packages/tl-api/src/tl_api/routes/punch.py`
- `packages/tl-api/src/tl_api/client/materials.py` (all), `client/__init__.py` (mixin tuple), `packages/tl-tui/src/tl_tui/client.py` (the materials block near line 921-1010), `embedded.py` (lines 1320-1340 and the materials block)
- `packages/tl-tui/tests/fakes_materials.py` (the command door and seed), `tests/fakes.py` (mixin and init lines)

## Allowed paths
- `packages/tl-api/src/tl_api/client/quality.py` (create), `client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_punch.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and init lines)
- `tests/api/test_client_punch.py` (create), `packages/tl-tui/tests/test_fakes_punch.py` (create)
- pins in union form, listed: `tests/api/test_client_roundtrip.py`, `packages/tl-tui/tests/test_remote_client.py`
- `docs/reports/P2-PUNCH/T04.md` (create)

## Acceptance
```
uv sync --all-packages
just check
just gate tests/api/test_client_punch.py packages/tl-tui/tests/test_fakes_punch.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
```

## Tests to add
- `tests/api/test_client_punch.py`: ledger built by commands (`punch_world.py` loaded by path; no projection writes); the embedded client and `ApiClient` over a `TestClient` give equal answers for the three reads; `quality_command("RaisePunchItem", ...)` and `ClearPunchItem` through both change state and the next read shows it; `VerifyPunchItem` by the clearer is refused with the S2 text on both; `RecordNotFoundError` with one text for a missing key on both; an item of a restricted source is absent for the lowest-clearance client. (D28: no case for an actor without `quality.view`; no account can lack it.) The test builds its own `db` and `World` (no conftest is added).
- `packages/tl-tui/tests/test_fakes_punch.py`: `seed_punch` counts, each filter narrows, `total` equals rows, counts by state, missing key raises `RecordNotFoundError`, `quality_command` is recorded.

## Escalation triggers
- A T03 model lacks a field the screens need; the roundtrip test needs a change other than a method list; `ClientInterface` already holds one of the names.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-PUNCH-T04: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
