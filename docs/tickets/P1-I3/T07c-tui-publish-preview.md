# P1-I3-T07c — TUI: the publish preview and the approval

Status: ready
Tier: haiku
Labels: tui
Depends on: S5, S6 (in the tree)
Branch: `p1/i3a-t07c-tui-publish-preview`

## Goal
A person sees what publishing a derived document would create, approves it with two key presses, and can take a publication back. `packages/tl-tui/src/tl_tui/widgets/publish_preview.py` has the layout, the bindings, `_offer`, the skip and view toggles and `action_reload`/`action_close` written; `reload`, `_fill`, `action_publish` and `action_compensate` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **ADR-0014 sections 5 and 6.** Publishing creates records through module commands as one correlated import; rows whose key exists need `skip_existing`. Publishing into tags needs the admin role, into documents the document controller (or admin) role; compensation needs admin and is all or nothing. The screen must not call the client for an action the person's role does not allow (the server would refuse it, and the screen says so first). Approval is two presses of the same key; Esc after the first press cancels the question.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/derive_text.py` (final; read only): `DERIVED_COLUMNS`, `JOB_COLUMNS`, `PLAN_COLUMNS`, `derived_cells`, `derived_detail_lines`, `report_lines`, `diff_lines`, `summary_line`, `job_cells`, `job_detail_lines`, `jobs_summary`, `plan_cells`, `plan_header_lines`, `can_apply`, `compensation_lines`, `next_choice`.
`tl_tui.client.ClientInterface` (read only), derivation part: `list_derived_documents`, `get_derived_document`, `list_processing_jobs`, `get_processing_job`, `get_derived_rows`, `get_derived_report`, `get_derived_diff`, `get_publish_preview`, `get_compensation_preview`, `start_extraction`, `validate_derived`, `cancel_job`, `publish_derived_tags`, `publish_derived_documents`, `compensate_publication`. Failures are the module's exceptions (`CLIENT_ERRORS`). Each stub already imports what its bodies need.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/publish_preview.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/derive_text.py`
- `packages/tl-tui/src/tl_tui/widgets/repin_dialog.py` (a confirming dialog, complete)
- `packages/tl-tui/tests/fakes_derivation.py` (the fake the test uses)
- `docs/tickets/P1-I3/provided/t07c-test_publish_preview.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages it checks; `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I3/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I3/P1-I3-T07c.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line.
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*.
Expected: `just check` clean; 7 pass.

## Allowed paths
- pytest runs in importlib mode: a test cannot import a sibling test file; `tests/fakes.py`, `fakes_derivation.py` and `helpers.py` are in the tree and read only (L-P0-I2-B1). The tests use `FakeClient.seed_derivation("P123")`.
- A table cell is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P0-I2-T13).
- The screens decide nothing: what a row says, whether a publication can go ahead and which role is needed come from `tl_tui/derive_text.py` and the client; do not rebuild text in the widget, and do not edit `derive_text.py`.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys do nothing while the filter input has focus where the screen has one (the letters are text).
- This ticket's test file has 7 test functions and no database fixture. The screen is mounted directly by the test and dismisses with `True` when records were created or taken back.

## Steps
- `packages/tl-tui/src/tl_tui/widgets/publish_preview.py` (edit)
- `packages/tl-tui/tests/test_publish_preview.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T07c.md` (create)

## Acceptance
```
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I3/provided/t07c-test_publish_preview.py.txt` to `packages/tl-tui/tests/test_publish_preview.py`.
3. Implement the four bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.
```
just check
uv run pytest packages/tl-tui/tests/test_publish_preview.py -q

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
