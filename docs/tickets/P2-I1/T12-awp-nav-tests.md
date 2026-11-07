# P2-I1-T12 — Pytest for the five awp palette entries

Status: ready (r12; T05h merged ff5943b)
Tier: haiku
Review: lite
Labels: tests, tui
Depends on: T05h (merged)
Branch: `p2/i1-t12-nav-tests`
Worktree: `/home/user/wt/i1/t12` (from `p2/i1` head)

## Goal
`packages/tl-tui/tests/test_awp_nav.py` pins the palette ids and that each entry opens its screen. It is the pytest form of the checks already in `dev/accept/P2-I1/T05h.py` (copy the structure; read it, do not change it).

## Interfaces (verbatim from the merged tree)
```python
# tl_tui.commands.APP_COMMANDS rows: AppCommand(id, label, keys, action)
# ids (pinned): cwps wbs cwas path packages ; keys == "" ; action == id ; TlApp.action_<id> exists
# screens: cwps CwpRegisterScreen (tl_tui.widgets.cwp_register), wbs WbsScreen (wbs_screen), cwas CwaRegisterScreen (cwa_register),
#          path PathScreen (path_screen), packages PackageLogScreen (package_log)
# labels: read them from APP_COMMANDS in the test, do not retype them
```

## Context (read these, nothing else)
- `dev/accept/P2-I1/T05h.py` (the harness: make_app, run, top_row, check_open, check_no_project)
- `packages/tl-tui/tests/helpers.py` (`run_pilot`, `settle`), `packages/tl-tui/tests/fakes_awp.py` (`seed_awp`)
- `packages/tl-tui/tests/test_palette.py` (pytest style)
may explore: (none)

## Allowed paths
- `packages/tl-tui/tests/test_awp_nav.py` (create)

## Tests to add (one function each)
1. ids: the five ids are in APP_COMMANDS, unique, `keys == ""`, `action == id`, `TlApp` has `action_<id>`.
2. `test_action_opens_<id>` for the five (parametrize): `app.action_<id>()` pushes the expected screen class; Esc returns to the base stack depth.
3. `test_palette_opens_<id>` for the five: open the palette, type the entry's label, the highlighted row's `command_id == id`, Enter opens the screen, Esc returns.
4. `test_no_project_scope_warns`: scope `"company"`: each action pushes no screen and raises one warning notice.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest packages/tl-tui/tests/test_awp_nav.py -q
```
Expected: all pass; ruff and pyright clean on the new file. No other test is run.

## Report requirements
`docs/reports/P2-I1/T12.md` (<= 60 lines): both command outputs (<= 5 lines each).

## Escalation triggers
- Stop and report *Blocked* if a test needs a change in `src/` or in `fakes*.py`, or the palette does not rank the label first.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
