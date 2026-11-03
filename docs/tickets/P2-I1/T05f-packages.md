# P2-I1-T05f — External packages log: Textual-free text module and screen

Status: ready (T05a merged at 1c6aed5; r8 split off the path screen, T05c)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a (merged)
Branch: `p2/i1-t05f-packages`
Worktree: `/home/user/wt/i1/t05f` (from `p2/i1` head)

## Goal
A `LogScreen` (spec §8 "External packages", skill `tui-layout`) with its text in `tl_tui/package_text.py`, which does not import `textual` (D27); the web reuses it. No actions bar entries in I1: `actions_for` returns `[]`. Not to be confused with `awp_text.PACKAGE_COLUMNS` (the package table inside a CWP page).

## Contract (fixed now; pure functions; PackageRow with title and cwps from T10c)
```python
# tl_tui/package_text.py
PACKAGE_COLUMNS = ("Number","Subject","Type","Status","Forecast","Actual","Constraint source","CWPs")   # Type is hidden by LogScreen when only one kind is present
def package_cells(row: PackageRow) -> tuple[str, ...]      # Constraint source "Yes"/"—"; CWPs = count
def package_summary(row: PackageRow) -> str                # "EWP · forecast 2026-11-20 · required by 3 CWPs"
def package_page(row: PackageRow, *, panel: bool = False, technical: bool = False) -> Page   # sections Dates (Forecast, Actual), Source (source system), CWPs (list of numbers; note "No CWPs require it")
```
The screen loads `list_packages(project)` once. Keys: `t` cycles type (all, EWP, PWP), `c` toggles constraint sources only, `F5` reload. `KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  t type  c constraints  F5 reload  Esc back`. Summary line `n packages` or `n of m packages` with the filters named.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (names and the helpers), `widgets/tag_register.py` (all; the screen pattern), `correspondence_text.py` (text-module pattern)
- `packages/tl-tui/src/tl_tui/layout.py` lines 98-146, `widgets/log_screen.py` lines 96-225, `tests/fakes_awp.py` (`seed_awp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/package_text.py`, `packages/tl-tui/src/tl_tui/widgets/package_log.py` (create); `dev/accept/P2-I1/T05f.py`, `docs/reports/P2-I1/T05f.md` (create).
- Do NOT edit `layout.py`, `awp_text.py` or the nav files (supervisor glue); name any needed `DROP_FIRST`/`SHORTENABLE` entry under *Open questions*.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05f.py                        # no pytest
```
`T05f.py` (Textual pilot on `FakeClient`; the seed has no packages, so add one EWP and one PWP to the fake list in the script): `PASS no textual` (import with `sys.modules["textual"] = None`); `PASS cells`; `PASS summary`; `PASS page` (with and without CWPs); `PASS keys` (`t`, `c` change the row count; Type column hidden when one kind); `PASS mount 80` and `PASS mount 170`; `PASS missing`. Ends `T05f ok`.

## Tests to add
none (T11: packages/tl-tui/tests/test_path_screen.py (the package log joins it)).

## Report requirements
`docs/reports/P2-I1/T05f.md` <= 60 lines; deviations first; tui-layout checklist answered line by line. Subject `P2-I1-T05f: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never add a call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
