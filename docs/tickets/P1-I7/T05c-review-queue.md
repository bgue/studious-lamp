# P1-I7-T05c — Review-queue screen (TUI)

Status: ready
Tier: haiku
Labels: tui
Depends on: — (the client seam and `integration_text.py` are in the tree)
Branch: `p1/i7a-t05c-review-queue`

## Goal
A person can review what the enrichers proposed from the terminal. `packages/tl-tui/src/tl_tui/widgets/review_queue.py` holds `ReviewQueueScreen`, opened with `Ctrl+R` (the app wiring is done and final). Its layout, bindings, `_say`, `_waiting`, `action_reload` and `action_close` are final; `reload`, `_fill`, `current`, `_describe`, `action_accept`, `action_reject` and `action_toggle_all` raise `NotImplementedError`. You implement them from the docstrings. One provided test file must pass.

## Brief references (pasted)
> **Brief 18.9 Enrichment.** "Acceptance policy is set per property: `auto` (above a confidence threshold), `propose` (a person accepts it in a review queue), or `shadow`. ... The review queue shows the proposed value, the confidence, the inputs and the enricher, and a person accepts or rejects it; a rejection takes a reason."
>
> **FANOUT D12.** "`AcceptEnrichment`, `RejectEnrichment`: user (the target type must allow `SetPsetValues`)." The service decides; a refusal is shown, nothing changes.
>
> **Why the details matter.** The screen holds no rule: it lists, asks, and reads the list again. A value that someone else decided meanwhile must show the service's refusal and leave the queue on the next read.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/client.py` (final; read only; the two methods the screen uses, plus settings):
```python
def list_integration(self, kind: str, *, state: str | None = None, limit: int = 200) -> list[dict[str, Any]]: ...
    # kind: apps | actions | rules | endpoints | enrichers | invocations | enrichments | deliveries
    # state filters enrichments (acceptance_state) and deliveries (state). A row is a dict of the
    # projection table with its JSON columns parsed; no secret and no payload is in one.
def integration_command(self, name: str, scope: str, **fields: Any) -> CommandResult: ...
    # the service judges the access of the signed-in person and raises ForbiddenError,
    # IntegrationStateError, IntegrationNotFoundError ... (all inside CLIENT_ERRORS)
def get_setting(self, key: str, *, project: str | None = None, user: str | None = None) -> SettingView: ...
    # SettingView.effective.value is the value (a bool for integration.kill_switch)
```
`packages/tl-tui/src/tl_tui/integration_text.py` (final; read only; plain text for the rows):
```python
COLUMNS: dict[str, tuple[str, ...]]          # column titles by kind
LABELS: dict[str, str]                       # the name of a kind on screen
def cells(kind: str, row: Mapping, names: Mapping[str, str] | None = None) -> tuple[str, ...]
def detail_lines(kind: str, row: Mapping, names: Mapping[str, str] | None = None) -> list[str]
```
`tl_tui.errors`: `CLIENT_ERRORS` (a tuple of exception types) and `describe_error(exc) -> str`.
`tl_tui.widgets.prompt.PromptScreen(title, label, *, initial="", required=True)`: a modal that dismisses with the entered text or `None` when cancelled (an empty answer stays open when `required`).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/review_queue.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/integration_text.py` (read only)
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (read only; a screen of the same shape)
- `packages/tl-tui/tests/rows_integration.py` and `tests/fakes_integration.py` (read only; the sample rows and the fake client the test uses)
- `docs/tickets/P1-I7/provided/t05c-test_review_queue.py.txt` (the test)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages: the stub's two lint-silencing header lines come out when you implement it (L-P1-I3-3).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean, and it was run against a reference implementation, with mutation checks (L-P1-I3-12).
- Commit your report at `docs/reports/P1-I7/P1-I7-T05c.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Keep every signature, widget id, key binding, printed text and status message exactly as the STEPS and the test say.
- Do not run `just test` or `just test-parity` (they take an hour and the box is shared). Run the acceptance commands once each.
- The test count below was counted from the provided file; a parametrized test counts once per case (L-P0-I8A-8).
- A Textual widget attribute named `_id` belongs to Textual (the reference hit it: `self._id(...)` crashed on mount). Use the names the stub gives you.
- A screen never stores state of its own beyond what the stub's `__init__` sets: every change is one client call and the list is read again afterwards (`self.reload()`).
- `describe_error(exc)` from `tl_tui.errors` is the only way an error is shown; the status line is `self._say(text, error=True)`, which prefixes `! `.
- Textual widgets are queried with `self.query_one("#id", Type)`; `DataTable.clear()` keeps the columns, `clear(columns=True)` drops them.
- Under the pilot, a key press needs `await pilot.pause()` before the screen is read. You do not write tests, so this matters only if one of yours hangs: run it again alone before changing code.

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/review_queue.py` (edit)
- `packages/tl-tui/tests/test_review_queue.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T05c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t05c-test_review_queue.py.txt` to `packages/tl-tui/tests/test_review_queue.py`.
3. Implement the methods that raise `NotImplementedError` by their docstrings (the paragraph that starts `STEPS`); remove the STUB paragraph, the STEPS paragraphs and the two lint-silencing lines. Keep the first sentence of each docstring.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_review_queue.py -q
```
Expected: `just check` clean; the provided test file passes (9 tests).

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree.
- Stop if the test needs a change outside *Allowed paths* (`app.py` and `commands.py` are the supervisor's and done).
- Never call a command other than `AcceptEnrichment` and `RejectEnrichment`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
