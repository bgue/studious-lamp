# P0-I3-T15 — Workflow action menu with guard-failure display

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (`TlApp.action_workflow`, `ClientInterface.workflow_status` and `transition`, the stub)
Branch: `p0/i3-t15-workflow-menu`

## Goal
`w` on the open record (or the grid cursor row) opens a menu with the record's workflow state, each transition that starts there marked allowed or
blocked, and below it the guards of the highlighted transition with their messages, so a blocked transition says why. Enter runs an allowed
transition. The app wiring (`TlApp.action_workflow`), the layout (`compose`), the constructor and the key bindings exist in
`tl_tui/widgets/workflow_menu.py`; the three pure functions and the methods marked `raise NotImplementedError` are the work. A provided test
file (12 tests) must pass.

## Brief references (pasted)
> **8 Workflow engine:** Declarative state machines per record type (states, transitions, guards, required psets, required links, approvers, signatures, notifications). **7.1:** missing expected links can act as workflow guards.
> **10.2 Record view:** Header (key, title, status, badges, **workflow actions**). Every action shows what blocks it (brief 10.3: meaning is never colour alone; pair status with a symbol).
> Roles are a stub list until auth exists: the menu passes the app's `roles` with the transition; nothing verifies them.

### Specification (the provided test checks it)
Pure functions (`WorkflowStatus`, `TransitionOption`, `GuardResult` are in the interfaces):
- `header_text(status)`: two lines joined by `"\n"`: `f"{status.key}  {status.workflow} v{status.workflow_version}"` and `f"State: {status.state_label}  (since {timestamp(status.entered_at)})"` (`timestamp` from `tl_tui.text` gives `2026-10-09 09:05`).
- `option_line(option)`: `f"{option.label} → {option.to_state}  {verdict}"` with `verdict` `"✓ allowed"` or `"✗ blocked"`.
- `guard_lines(option)`: one `f"  {'✓' if g.passed else '✗'} {g.kind}: {g.message}"` per guard; `["  (no guards)"]` when there are none.

`WorkflowMenu` (a `ModalScreen[bool]`; `compose` yields `Static#wf-header`, `OptionList#wf-options`, `Static#wf-guards`, `Static#wf-status`; `__init__` sets `client`, `scope`, `record`, `roles` (tuple), `actor`, `status` (`None`)):
- `on_mount`: focus `#wf-options`, then `_load()`.
- `_say(text)`: update `#wf-status`.
- `_load()`: clear the option list. `self.status = self.client.workflow_status(self.record["id"], roles=self.roles)`; on `CLIENT_ERRORS`: `self.status = None`, set `#wf-header` to the record's key (`str(self.record.get("key") or "")`), clear `#wf-guards`, `_say(describe_error(exc))`, return. Otherwise set `#wf-header` to `f"{header_text(status)}\nRoles: {roles}"` where `roles` is `", ".join(self.roles)` or `"none"`; add one `Option(Text(option_line(o)), id=o.transition)` per option (**`rich.text.Text`**, not a plain string); highlight index 0 when there are options, else set `#wf-guards` to `"No transitions from this state"`; then `_show_guards()`.
- `_highlighted() -> TransitionOption | None`: the option at the list's highlighted index, `None` without a status or an in-range index.
- `_show_guards()`: when an option is highlighted, set `#wf-guards` to `"\n".join(guard_lines(option))`.
- `on_option_list_option_highlighted(event)`: `event.stop()`, `_show_guards()`. `on_option_list_option_selected(event)`: `event.stop()`, `_run(self._highlighted())`.
- `action_move(delta)`: the list's `action_cursor_down()` for `delta > 0`, else `action_cursor_up()`.
- `_run(option)`: do nothing without an option or a status. If `not option.allowed`: `_say("Blocked: " + "; ".join(messages of the guards that did not pass))` and return (stay open). Otherwise `TransitionWorkflow(actor=self.actor, source="tui", scope=self.scope, stream_id=str(self.record["id"]), expected_version=status.version, transition=option.transition, actor_roles=list(self.roles))` → `self.client.transition(cmd)`. On `GuardFailedError` (a guard changed meanwhile): `_load()` then `_say(f"Blocked: {exc}")`. On other `CLIENT_ERRORS`: `_say(describe_error(exc))`. On success `self.dismiss(True)`.
- `action_close()`: `self.dismiss(False)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. `Static` and `OptionList` parse `[...]` as markup: use `markup=False` / `rich.text.Text`.
- Do not name an attribute after a Textual DOM property. `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `Option`, `GuardFailedError`, `CLIENT_ERRORS`, `describe_error`, `timestamp`, `TransitionWorkflow`).
- Remove the `STUB (P0-I3-T15)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/workflow_menu.py (existing stub; keep every name and signature)
def header_text(status: WorkflowStatus) -> str; def option_line(option: TransitionOption) -> str; def guard_lines(option: TransitionOption) -> list[str]
class WorkflowMenu(ModalScreen[bool]):
    def __init__(self, client: ClientInterface, scope: str, record: dict[str, Any], *, roles: Sequence[str] = (), actor: str = "user:dev") -> None
```
```python
# existing (tl_core.services.workflow)
class TransitionOption(BaseModel): transition: str; label: str; from_state: str; to_state: str; allowed: bool; guards: list[GuardResult]
class WorkflowStatus(BaseModel): record_id; key: str | None; workflow: str; workflow_version: int; state: str; state_label: str; entered_at: str; version: int; options: list[TransitionOption]
class TransitionWorkflow(Command): stream_id: str; expected_version: int; transition: str; actor_roles: list[str] = []; reason: str | None = None
# tl_core.workflow.engine.GuardResult: kind: str; passed: bool; message: str; details: dict
# tl_core.services.errors.GuardFailedError (a ServiceError; .results lists every guard)
# ClientInterface: workflow_status(record_id, *, roles=()) -> WorkflowStatus;  transition(cmd: TransitionWorkflow) -> CommandResult
# tl_tui.errors: CLIENT_ERRORS, describe_error(exc) -> str;  tl_tui.text.timestamp(value) -> "2026-10-09 09:05"
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/workflow_menu.py`
- `packages/tl-tui/src/tl_tui/widgets/help_screen.py` (style of a modal)
- `packages/tl-tui/tests/fakes.py` and `packages/tl-tui/tests/fakes_links.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_workflow_menu.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/workflow_menu.py` (edit)
- `packages/tl-tui/tests/test_workflow_menu.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T15.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_workflow_menu.py.txt packages/tl-tui/tests/test_workflow_menu.py`
2. Implement the three functions and the methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_workflow_menu.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_workflow_menu.py.txt packages/tl-tui/tests/test_workflow_menu.py
```
Expected: 12 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `app.py`, the fakes or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
