# P2-I1-T05c — Path of construction: Textual-free text module and screen

Status: ready (T05a merged at 1c6aed5; r8 split off the packages log, T05f)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a (merged)
Branch: `p2/i1-t05c-path`
Worktree: `/home/user/wt/i1/t05c` (from `p2/i1` head)

## Goal
A `LogScreen` (spec §8 "Path of construction", skill `tui-layout`) with its text in `tl_tui/path_text.py`, which does not import `textual` (D27); the web reuses it. No actions bar entries in I1: `actions_for` returns `[]`.

## Contract (fixed now; pure functions; PathView, PathStep, PathVersion, CwaRow, CwpRow from tl_mod_awp.views)
```python
# tl_tui/path_text.py
PATH_COLUMNS = ("Number","Subject","Reason","CWPs","Budget h"); PATH_RIGHT = ("Number","CWPs","Budget h")   # Number = position
@dataclass(frozen=True) class PathLine: step: PathStep; title: str | None; cwps: tuple[CwpRow, ...]
def path_lines(view: PathView, cwas: Sequence[CwaRow], cwps: Sequence[CwpRow]) -> list[PathLine]   # Subject "CWA code · name" ("code" alone when the area is unreadable); step.cwa None -> "—"
def path_cells(line: PathLine, labels: Labels | None = None) -> tuple[str, ...]                  # Reason = PathReason label of reason_code, "—" when none
@dataclass(frozen=True) class Moved: cwa: str | None; before: int | None; after: int | None
def compare_versions(old: PathView, new: PathView) -> list[Moved]          # key v; mark(m) -> "↑2" (moved earlier), "↓1", "" unchanged, "new"/"gone"; rows in the new order, gone last
def compare_cells(m: Moved) -> tuple[str, ...]                             # Before / After / mark
def version_heading(view: PathView) -> str                                 # "Path of construction · version 4"
def path_page(view: PathView, versions: Sequence[PathVersion], line: PathLine | None, *, panel: bool = False) -> Page
    # identity = version_heading; state line "Re-sequenced 2026-10-29 by A. Ruiz · reason Access" from the version row (date, who, reason of the first changed step; "Version 1" reads "Defined 2026-... by ...");
    # sections Steps changed (table Position/CWA/Reason versus the previous version), Versions (table Version/Date/Who/Reason, current marked)
```
Keys: `[` and `]` previous/next version (client `get_path(project, version=)`), `v` compare with the previous version, `F5` reload. Loads: `get_path`, `list_path_versions`, `list_cwas`, `list_cwps`. `KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  [ ] version  v compare  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` (names and the helpers), `widgets/tag_register.py` (all; the screen pattern), `correspondence_text.py` (text-module pattern)
- `packages/tl-tui/src/tl_tui/layout.py` lines 98-146, `widgets/log_screen.py` lines 96-225, `tests/fakes_awp.py` (`seed_awp`), `display.py` (`code_label`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/path_text.py`, `packages/tl-tui/src/tl_tui/widgets/path_screen.py` (create); `dev/accept/P2-I1/T05c.py`, `docs/reports/P2-I1/T05c.md` (create).
- Do NOT edit `layout.py`, `awp_text.py` or the nav files (supervisor glue); name any needed `DROP_FIRST`/`SHORTENABLE` entry under *Open questions*.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05c.py                        # no pytest
```
`T05c.py` (Textual pilot on `FakeClient` + `seed_awp`; if the fake has one version only, build a second `PathView` in the script): `PASS no textual` (import with `sys.modules["textual"] = None`); `PASS lines`; `PASS compare` (v1 against v2 with the moved marks `↑`, `↓`, `new`, `gone`); `PASS page` (state line for version 1 and for a re-sequence); `PASS keys` (`[`, `]`, `v`); `PASS mount 80` and `PASS mount 170`; `PASS missing` (an error from `get_path` shows a status). Ends `T05c ok`.

## Tests to add
none (T11: packages/tl-tui/tests/test_path_screen.py).

## Report requirements
`docs/reports/P2-I1/T05c.md` <= 60 lines; deviations first; tui-layout checklist answered line by line. Subject `P2-I1-T05c: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never add a call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
