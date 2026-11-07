# P2-I1-T05h — Palette entries and app actions for the five awp screens

Status: ready (T05g, T05c merged; all five screens exist)
Tier: haiku
Review: full
Labels: tui
Depends on: T05b T05c T05d T05e T05f (merged)
Branch: `p2/i1-t05h-nav`
Worktree: `/home/user/wt/i1/t05h` (from `p2/i1` head)

## Goal
Every awp screen is reachable from the command palette (and so from the tour and a screenshot): five keyless `AppCommand` rows and five app actions that open the screen for the scope's project. Same pattern as the P2-I3 materials logs (`_push_materials`, palette only, no key). No `keymap.py` row: a free function key is a later owner call (D53).

## Contract (fixed now)
`commands.py`, after the `tags` row (key `""`, like the P2-I3 rows):
```python
AppCommand("cwps", "Work packages: CWPs, state, budget, allocation", "", "cwps"),
AppCommand("wbs", "WBS: the work breakdown tree and its cost codes", "", "wbs"),
AppCommand("cwas", "Work areas: CWAs and their order on the path", "", "cwas"),
AppCommand("path", "Path of construction: the order of the areas, by version", "", "path"),
AppCommand("packages", "External packages: EWP and PWP, forecast and actual", "", "packages"),
```
`app.py`, next to `action_tags` (one helper plus five one-line actions; imports inside the helper):
```python
def _push_awp(self, which: str) -> None:
    """Open an awp screen of this project (P2-I1; palette entries, no key)."""
    if self._modal_open(): return
    project = project_of_scope(self.scope)          # tl_core.settings.layers, as action_tags
    if project is None:
        self.notify("The work packaging screens need a project.", severity="warning"); return
    # which: cwps -> widgets.cwp_register.CwpRegisterScreen, wbs -> widgets.wbs_screen.WbsScreen,
    # cwas -> widgets.cwa_register.CwaRegisterScreen, path -> widgets.path_screen.PathScreen,
    # packages -> widgets.package_log.PackageLogScreen; each (self.client, project)
def action_cwps(self) -> None: self._push_awp("cwps")      # likewise wbs, cwas, path, packages
```
Action names `cwps wbs cwas path packages`: grep `app.py` first that none exists already (`action_path` would clash with nothing today; if one does, stop and report).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/commands.py` (all), `packages/tl-tui/src/tl_tui/app.py` lines 625-660 (`action_tags`, `action_settings`)
- `packages/tl-tui/tests/test_palette.py` lines 1-60 and 295-312 (how the palette and `TlApp` are driven), `dev/accept/P2-I1/T05d.py` (script pattern: pilot, `FakeClient`, `seed_awp`)
may explore: `git show p2/i3:packages/tl-tui/src/tl_tui/app.py` lines 648-700 (`_push_materials`, the pattern)

## Allowed paths
- `packages/tl-tui/src/tl_tui/commands.py`, `packages/tl-tui/src/tl_tui/app.py` (edit, additions only)
- `dev/accept/P2-I1/T05h.py`, `docs/reports/P2-I1/T05h.md` (create)
- Do NOT edit `keymap.py`, `help` text, any screen file, `layout.py`, or tests. Expected diff about 60 lines.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05h.py                        # no pytest
```
`T05h.py` (pilot on `TlApp(FakeClient + seed_awp(...), project scope)` as T05d.py does): `PASS commands` (the five ids are in `APP_COMMANDS`, keys all `""`, ids unique, each `action_<action>` exists on `TlApp`); for each of the five: `PASS open <id>` (run the palette command by id, or call the action, inside the pilot; `app.screen` is the expected class; `Esc` returns to the first screen); `PASS no project` (scope `company`: the action pushes nothing, `app.screen_stack` length unchanged, a warning notice is raised). Ends `T05h ok`.

## Tests to add
none (T11 adds `test_awp_nav.py` after this merges; the script is the check).

## Report requirements
`docs/reports/P2-I1/T05h.md` <= 60 lines: deviations first, changed files, command output (<= 5 lines per command), open questions. State whether the palette finds each entry by typing its id.

## Escalation triggers
- Stop and report *Blocked* if an `action_` name above already exists, if a screen constructor takes more than `(client, project)`, or if a test outside Allowed paths breaks (rule 12: update it only if the break is the new rows; list it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
