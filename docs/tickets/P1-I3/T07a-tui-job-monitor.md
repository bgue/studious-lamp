# P1-I3-T07a — TUI: the job monitor

Status: ready
Tier: haiku
Labels: tui
Depends on: S6 (in the tree)
Branch: `p1/i3a-t07a-tui-job-monitor`

## Goal
A person sees the processing jobs of a project (or of one derived document), watches a queued job run, and cancels a queued one. `packages/tl-tui/src/tl_tui/widgets/job_monitor.py` has the layout, the bindings, the refresh timer, the event handlers and the actions `action_state_filter`, `action_reload` and `action_close` written; `reload`, `_fill`, `_describe` and `action_cancel` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **ADR-0014.** Jobs are `ProcessingJob` records; a worker claims them. Only a queued job can be cancelled; any signed-in person may start and cancel.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/derive_text.py` (final; read only): `DERIVED_COLUMNS`, `JOB_COLUMNS`, `PLAN_COLUMNS`, `derived_cells`, `derived_detail_lines`, `report_lines`, `diff_lines`, `summary_line`, `job_cells`, `job_detail_lines`, `jobs_summary`, `plan_cells`, `plan_header_lines`, `can_apply`, `compensation_lines`, `next_choice`.
`tl_tui.client.ClientInterface` (read only), derivation part: `list_derived_documents`, `get_derived_document`, `list_processing_jobs`, `get_processing_job`, `get_derived_rows`, `get_derived_report`, `get_derived_diff`, `get_publish_preview`, `get_compensation_preview`, `start_extraction`, `validate_derived`, `cancel_job`, `publish_derived_tags`, `publish_derived_documents`, `compensate_publication`. Failures are the module's exceptions (`CLIENT_ERRORS`). Each stub already imports what its bodies need.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/job_monitor.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/derive_text.py`
- `packages/tl-tui/src/tl_tui/widgets/document_register.py` (the same pattern, complete)
- `packages/tl-tui/tests/fakes_derivation.py` (the fake the test uses)
- `docs/tickets/P1-I3/provided/t07a-test_job_monitor.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages it checks; `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I3/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I3/P1-I3-T07a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line.
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*.
Expected: `just check` clean; 6 pass.

## Allowed paths
- pytest runs in importlib mode: a test cannot import a sibling test file; `tests/fakes.py`, `fakes_derivation.py` and `helpers.py` are in the tree and read only (L-P0-I2-B1). The tests use `FakeClient.seed_derivation("P123")`.
- A table cell is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P0-I2-T13).
- The screens decide nothing: what a row says, whether a publication can go ahead and which role is needed come from `tl_tui/derive_text.py` and the client; do not rebuild text in the widget, and do not edit `derive_text.py`.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys do nothing while the filter input has focus where the screen has one (the letters are text).
- This ticket's test file has 6 test functions and uses no database fixture, so it runs once whatever `--adapters` says (L-P1-I1-6). The screen is mounted directly by the test.

## Steps
- `packages/tl-tui/src/tl_tui/widgets/job_monitor.py` (edit)
- `packages/tl-tui/tests/test_job_monitor.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T07a.md` (create)

## Acceptance
```
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I3/provided/t07a-test_job_monitor.py.txt` to `packages/tl-tui/tests/test_job_monitor.py`.
3. Implement the four bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.
```
just check
uv run pytest packages/tl-tui/tests/test_job_monitor.py -q

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change in `derive_text.py`, the fake or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
