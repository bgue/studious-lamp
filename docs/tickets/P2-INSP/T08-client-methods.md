# P2-INSP-T08 - Inspection and checklist read methods and the fake

Status: ready (written r5; base `p2/ip-r3`; INSP-S2, T01 and T06 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, access
Depends on: P2-INSP-T01 (views), P2-INSP-T06 (routes), merged
Branch: `p2/insp-t08-client`
Worktree: `/home/user/wt/insp/t08` (from `p2/ip-r3`)

## Goal
Four read methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, and the existing `quality_command` door accepts the eleven inspection and checklist commands, so the terminal screens of T10 read inspections and checklists and run their commands from any of them. Pattern: `docs/tickets/P2-PUNCH/T04-client-methods.md` and its merged result (`tl_api/client/quality.py`, `embedded.py` `quality_command`, `fakes_punch.py`); extend those files, do not make a second mixin.

## Interfaces (same names, parameters and errors on every implementation)
```python
def list_inspections(self, project, *, state=None, point=None, area=None, inspector=None, subject=None, for_key=None, limit=200) -> InspectionPage
def get_inspection(self, project, key) -> InspectionDetail        # RecordNotFoundError("no inspection"): missing, hidden, other project: one text
def list_checklists(self, project, *, state=None, discipline=None, limit=200) -> ChecklistPage
def get_checklist(self, project, key) -> ChecklistDetail          # RecordNotFoundError("no checklist")
def quality_command(self, name, cmd) -> CommandResult             # existing; name may now be any model of QUALITY_COMMANDS
```
Types are the dataclasses of `tl_mod_quality.insp_views`. Routes: T06 (`for_key` is the `for` query, `subject` the `subject` query). `ApiClient` decodes with `TypeAdapter` as the punch methods do. Embedded: the same calls the routes make, under the signed-in viewer, after the same `quality.view` check on `project:P`; never a second SQL path; a bad `state` or `point` is the views' `ValueError`, surfaced as the punch methods surface theirs. `quality_command`: widen the accepted names from `PUNCH_COMMANDS` to `QUALITY_COMMANDS` (`tl_mod_quality.module`) in both implementations; an unknown name keeps its present error; a command names its record by `id` (the `.id` of the row types, as the punch commands do). Fake: answers from lists a test gives it (`load_inspections`, `load_checklists`), filters like the views, records each command in the list the punch fake uses; `seed_inspections(client)` makes 6 inspections (Planned, Scheduled hold point, Done reject, Verified, Cancelled, one for an IWP key) and 3 checklists (Draft, Published, Retired).

## Context (read these, nothing else)
- `docs/reports/P2-IP/INSPT06.md`, `packages/tl-api/src/tl_api/routes/insp.py`, `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (dataclasses and signatures only)
- `packages/tl-api/src/tl_api/client/quality.py` (whole), `packages/tl-tui/src/tl_tui/client.py` (the punch block near line 1020-1060), `packages/tl-tui/src/tl_tui/embedded.py` (punch block near line 1800-1860)
- `packages/tl-tui/tests/fakes_punch.py`, `tests/fakes.py` (mixin and init lines), `tests/api/test_client_punch.py` (the pattern of the roundtrip test)
- `packages/tl-modules/quality/tests/insp_world.py`

## Allowed paths
- `packages/tl-api/src/tl_api/client/quality.py`, `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py` (edit)
- `packages/tl-tui/tests/fakes_insp.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and init lines)
- `tests/api/test_client_insp.py` (create), `packages/tl-tui/tests/test_fakes_insp.py` (create)
- pins in union form, listed (rule 12): `tests/api/test_client_roundtrip.py`, `packages/tl-tui/tests/test_remote_client.py`, `packages/tl-tui/tests/test_client_module_roles.py` if they fail by method list only
- `docs/reports/P2-INSP/T08.md` (create)

## Tests to add
- `tests/api/test_client_insp.py` (ledger built by commands from `insp_world.py`, loaded by path; no projection writes): the embedded client and `ApiClient` over a `TestClient` give equal answers for the four reads; `quality_command("PlanInspection", ...)`, `ScheduleInspection` and `RecordInspectionResult` through both change state and the next read shows it; `VerifyInspection` by the recorder is refused with the S2 text on both; one `RecordNotFoundError` text for a missing inspection and checklist key on both; an inspection of a restricted subject is absent from the list (and its total) and answers the missing text for `get_inspection` for the lowest-clearance client; a punch command still runs through the same door.
- `packages/tl-tui/tests/test_fakes_insp.py`: `seed_inspections` counts, each filter narrows, `total` equals rows, missing key raises, `quality_command` is recorded.

## Acceptance
```
uv run ruff format --check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_insp.py
uv run ruff check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_insp.py
uv run pyright packages/tl-api/src/tl_api/client/quality.py packages/tl-tui/src/tl_tui/client.py packages/tl-tui/src/tl_tui/embedded.py packages/tl-tui/tests/fakes_insp.py tests/api/test_client_insp.py packages/tl-tui/tests/test_fakes_insp.py
just gate tests/api/test_client_insp.py packages/tl-tui/tests/test_fakes_insp.py
just gate tests/api/test_client_punch.py packages/tl-tui/tests/test_fakes_punch.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright, never `packages/tl-api/tests/test_commands.py`.

## Escalation triggers
A T06 model lacks a field the screens need; `ClientInterface` already holds one of the names; the roundtrip test needs a change other than a method list.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. Commit subjects `P2-INSP-T08: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
