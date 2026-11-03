# P2-I1-T05e — CWA register: Textual-free text module and screen

Status: ready (T05a merged at 1c6aed5; r8 split off the WBS tree, T05b)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a (merged)
Branch: `p2/i1-t05e-cwa`
Worktree: `/home/user/wt/i1/t05e` (from `p2/i1` head)

## Goal
A `LogScreen` (spec §8 "CWA register", skill `tui-layout`) with its text in `tl_tui/cwa_text.py`, which does not import `textual` (D27); the web reuses it. `hours_text`, `date_text` come from `awp_text`. No actions bar entries in I1: `actions_for` returns `[]`.

## Contract (fixed now; pure functions; CwaRow, CwpRow, PathView from tl_mod_awp.views)
```python
# tl_tui/cwa_text.py
CWA_COLUMNS = ("Number","Subject","Position","CWPs","Budget h"); CWA_RIGHT = ("Position","CWPs","Budget h")
@dataclass(frozen=True) class CwaLine: row: CwaRow; position: int | None; cwps: tuple[CwpRow, ...]; steps: int   # steps = len(path.steps), 0 without a path
def cwa_lines(cwas: Sequence[CwaRow], path: PathView | None, cwps: Sequence[CwpRow]) -> list[CwaLine]   # position from path.steps (cwa code), cwps with row.cwa == code; ordered by position, absent last, then code
def visible_lines(lines, show_retired: bool) -> list[CwaLine]           # key r
def cwa_cells(line: CwaLine) -> tuple[str, ...]; def cwa_summary(line) -> str   # "Position 3 of 12 · 4 CWPs · 11 300 h"
def cwa_page(line: CwaLine, *, panel: bool = False, technical: bool = False) -> Page   # sections Location, CWPs (table Number/Subject/State/Budget h); Files and Links are omitted until a view carries counts (say so in the report)
```
The screen loads `list_cwas`, `get_path`, `list_cwps` (three client calls, no per-row call). Keys: `r` show/hide retired, `F5` reload. `KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  r retired  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (names and the helpers), `widgets/tag_register.py` (all; the screen pattern), `correspondence_text.py` (text-module pattern)
- `packages/tl-tui/src/tl_tui/layout.py` lines 98-146, `widgets/log_screen.py` lines 96-225, `tests/fakes_awp.py` (`seed_awp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/cwa_text.py`, `packages/tl-tui/src/tl_tui/widgets/cwa_register.py` (create); `dev/accept/P2-I1/T05e.py`, `docs/reports/P2-I1/T05e.md` (create).
- Do NOT edit `layout.py`, `awp_text.py` or the nav files (supervisor glue); name any needed `DROP_FIRST`/`SHORTENABLE` entry under *Open questions*.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05e.py                        # no pytest
```
`T05e.py` (Textual pilot on `FakeClient` + `seed_awp`): `PASS no textual` (import with `sys.modules["textual"] = None`); `PASS lines` (positions from the path, CWPs per area, ordering); `PASS page`; `PASS retired` (key `r` changes the row count; add a retired CWA to the fake list); `PASS mount 80` and `PASS mount 170` (no line wider than the terminal; Subject not right of the third column; panel at 170 shows heading, state, summary); `PASS missing`. Ends `T05e ok`.

## Tests to add
none (T11: packages/tl-tui/tests/test_cwa_register.py).

## Report requirements
`docs/reports/P2-I1/T05e.md` <= 60 lines; deviations first; tui-layout checklist answered line by line. Subject `P2-I1-T05e: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never add a call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
