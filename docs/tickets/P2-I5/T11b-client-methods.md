# P2-I5-T11b — client methods and fakes: progress, weeks, look-ahead, KPIs, counts and the two command doors

Status: staged (dispatch after T11a1 and T11a2 merge; read their reports for the route model names)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, api, read, confidentiality
Depends on: T11a1, T11a2, S4b
Branch: `p2/i5-t11b-client-methods`
Worktree: harness-created under `/home/user/wt/i5/t11b` (from `p2/i5` head)

## Goal
Eleven read methods and two command methods exist on `ClientInterface` (`tl_tui/client.py`), the embedded client, `ApiClient` and `FakeClient`, so the screens (T06a, T06b, T06c1, T06c2) and the pack read and write through any of them. Pattern: P2-I2 T04c2 (`docs/tickets/P2-I2/T04c2-client-methods.md`; the IWP methods are the model: `tl_api/client/iwp.py`, `embedded.py` ~1831-1880, `client.py` ~1060-1095, `tests/fakes_iwp.py`). `RemoteClient` passes through unchanged.

## Interfaces (add to `ClientInterface`; same names, parameters and errors on all three)
```python
# route models of T11a1/T11a2 (names in their reports); module models as named
def list_iwp_counts(self, project) -> list[IwpCountRow]
def get_iwp_progress(self, project, number) -> IwpProgress              # RecordNotFoundError (missing or hidden: one text)
def get_progress_rollup(self, project) -> RollupBody
def get_iwp_hash(self, project, number) -> IwpHash                      # RecordNotFoundError; the value a sign-off carries
def list_kpis(self, project) -> list[KpiTile]                           # tl_mod_awp.kpis
def list_weekly_plans(self, project, *, limit=60) -> list[week_views.WeekRow]
def get_weekly_plan(self, project, week) -> week_views.WeekDetail       # RecordNotFoundError
def list_miss_reasons(self, project) -> list[str]
def get_look_ahead(self, project, schedule, *, snapshot=None, weeks=4) -> LookAheadView   # the DATACLASS (look_ahead_view.py)
def awp_command(self, name: str, cmd: Command) -> CommandResult         # a model of AWP_COMMANDS; else ForbiddenError("<name> is not an awp command")
def constraint_command(self, name: str, cmd: Command) -> CommandResult  # a model of tl_core.constraints.commands.command_table(); else ForbiddenError
```
- Routes (T11a1, T11a2): `GET /projects/{p}/awp/{iwps/counts, iwps/{n}/progress, iwps/{n}/hash, progress/rollup, kpis, weeks, weeks/{week}, miss-reasons, look-ahead}`. `ApiClient.get_look_ahead` rebuilds the dataclass from `LookAheadBody` (`LookAheadView(..., items=tuple(LookAheadItem(row=LookAheadRow(**i.row.model_dump()), iwps=tuple(LookAheadIwp(**x.model_dump()) for x in i.iwps))))`); embedded returns what `look_ahead_view` returns.
- Commands: `ApiClient._command(name, cmd)` (`POST /commands/<name>`, token's actor) after the name/class check, as `materials_command` (`tl_api/client/materials.py` 135-144). Embedded, as `materials_command` (`embedded.py` 1749-1756): `self._uow(False)`, `self._own_command(cmd.actor)`, `self._command_gate(uow, cmd)`, `self.own_writes.note(spec.handler(uow, cmd))`, with `spec` found in `AWP_COMMANDS` (awp) or `command_table()` (constraint) by `model.__name__`.
- Embedded reads: the same calls the routes make, under the signed-in viewer (`self._uow(True)` sets it). Never a second SQL path.
- Fake (`tests/fakes_week.py`): answers from lists a test loads (`load_weeks(project, plans: dict[str, WeekDetail])`, `load_progress(project, {number: IwpProgress}), `load_hashes``, `load_counts`, `load_kpis`, `load_look_ahead(project, view)`, `load_miss_reasons`), filters and sorts like the readers, `RecordNotFoundError` for an unloaded week or number; `awp_command` and `constraint_command` append `(name, cmd)` to `self.sent` and return a `CommandResult` (stream id `"fake"`, version 1), or raise `self.command_error` when a test sets it. `seed_week(client)` loads two plans (one Closed, ppc 66.7 with 3 commitments; one Committed), 3 counts rows, 2 KPI tiles, one look-ahead (2 activities, 2 IWPs), 3 miss reasons.

## Context (read these, nothing else)
- `docs/reports/P2-I5/{T11a1,T11a2}.md`, `packages/tl-api/src/tl_api/routes/{awp_progress,awp_weeks}.py`
- `packages/tl-api/src/tl_api/client/{iwp.py, materials.py (135-144), __init__.py (mixin tuple)}`
- `packages/tl-tui/src/tl_tui/client.py` (1055-1095), `embedded.py` (1749-1756, 1831-1880), `tests/fakes_iwp.py` (1-60, 100-140), `tests/fakes.py` (the mixin and `_init_iwp()` lines)

## Allowed paths
- `packages/tl-api/src/tl_api/client/awp_weeks.py` (create), `client/__init__.py` (import and one tuple entry)
- `packages/tl-tui/src/tl_tui/client.py`, `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/tests/fakes_week.py` (create), `packages/tl-tui/tests/fakes.py` (mixin and `_init_week()` lines)
- `dev/accept/P2-I5/T11b.py` (create), `docs/reports/P2-I5/T11b.md`; consequential pins (union): `tests/api/test_client_roundtrip.py` method lists

## Acceptance
```
uv sync --frozen --all-packages
just check
uv run python dev/accept/P2-I5/T11b.py
just gate tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py packages/tl-tui/tests/test_client_awp.py
```
`T11b.py` (a SQLite ledger from `WeekWorld`/`ScheduleWorld`; embedded client on it, `ApiClient` over a `TestClient` of the app on a copy, `seed_week(FakeClient())`): `PASS <method> <n>` for the eleven reads on each of the three; `PASS same` embedded and ApiClient equal for `get_weekly_plan`, `get_iwp_progress`, `get_iwp_hash`, `list_iwp_counts`, `get_look_ahead`, `list_kpis`; `PASS missing` all three raise `RecordNotFoundError` for week `2099-W01` and number `NO-SUCH`; `PASS hidden` a low-clearance reader gets the same error text for a hidden plan as for a missing one; `PASS door` an `awp_command` of a non-awp model and a `constraint_command` of an awp model are `ForbiddenError` on all three; `PASS write` embedded `awp_command("OpenWeeklyPlan", ...)` then `get_weekly_plan` shows it. Ends `T11b ok`.

## Tests to add
None beyond the script and the roundtrip pins.

## Escalation triggers
- A T11a model lacks a field this ticket names; `ClientInterface` already holds one of the names; the roundtrip test needs a change other than a method list.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T11b: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
