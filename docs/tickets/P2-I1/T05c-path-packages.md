# P2-I1-T05c — Path of construction and external packages: Textual-free text modules and screens

Status: draft (r8: split by area to pass the Haiku size check, then ready when T05a is merged)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a
Branch: `p2/i1-t05c-path-packages`
Worktree: `/home/user/wt/i1/t05c` (from `p2/i1` head)

## Goal
Two `LogScreen`s (spec §8 "Path of construction", "External packages") with text in `tl_tui/path_text.py` and `tl_tui/package_text.py`, neither importing `textual` (D27); the web reuses them.

## Contract (fixed now; pure functions)
```python
# tl_tui/path_text.py   (PathView, PathStep, PathVersion, CwaRow, CwpRow from tl_mod_awp.views)
PATH_COLUMNS = ("Number","Subject","Reason","CWPs","Budget h"); PATH_RIGHT = ("Number","CWPs","Budget h")   # Number = position
@dataclass(frozen=True) class PathLine: step: PathStep; title: str | None; cwps: tuple[CwpRow, ...]
def path_lines(view: PathView, cwas: Sequence[CwaRow], cwps: Sequence[CwpRow]) -> list[PathLine]   # Subject "CWA code · name" ("code" alone when the area is unreadable); step.cwa None -> "—"
def path_cells(line: PathLine, labels: Labels | None = None) -> tuple[str, ...]                  # Reason = PathReason label of reason_code, "—" when none
@dataclass(frozen=True) class Moved: cwa: str | None; before: int | None; after: int | None
def compare_versions(old: PathView, new: PathView) -> list[Moved]          # key v; mark(m) -> "↑2" (moved earlier), "↓1", "" unchanged, "new"/"gone"; rows in the new order, gone last
def compare_cells(m: Moved) -> tuple[str, ...]                             # Before / After / mark
def version_heading(view: PathView) -> str                                 # "Path of construction · version 4"
def path_page(view: PathView, versions: Sequence[PathVersion], line: PathLine | None, *, panel: bool = False) -> Page
    # identity = version_heading; state line "Re-sequenced 2026-10-29 by A. Ruiz · reason Access" from the version row (date, who, reason of the first changed step; "Version 1" has "Defined 2026-... by ...");
    # sections Steps changed (table Position/CWA/Reason versus the previous version), Versions (table Version/Date/Who/Reason, current marked)
# tl_tui/package_text.py   (PackageRow; title and cwps from T10c)
PACKAGE_COLUMNS = ("Number","Subject","Type","Status","Forecast","Actual","Constraint source","CWPs")   # Type is hidden by LogScreen when only one kind is present
def package_cells(row: PackageRow) -> tuple[str, ...]      # Constraint source "Yes"/"—"; CWPs = count
def package_summary(row: PackageRow) -> str                # "EWP · forecast 2026-11-20 · required by 3 CWPs"
def package_page(row: PackageRow, *, panel: bool = False, technical: bool = False) -> Page   # sections Dates (Forecast, Actual), Source (source system), CWPs (list of numbers; note "No CWPs require it")
```
Keys: `[` `]` version (client `get_path(version=)`), `v` compare with the previous version. Loads: `get_path`, `list_path_versions`, `list_cwas`, `list_cwps` (path screen); `list_packages` (package log).

## Context, Allowed paths, Acceptance
- Context: `awp_text.py` (T05a, merged), `widgets/tag_register.py` (screen pattern), `correspondence_text.py`, `layout.py` lines 98-146, `display.py` (`code_label`), `tests/fakes_awp.py`.
- Allowed: `tl_tui/path_text.py`, `tl_tui/package_text.py`, `widgets/path_screen.py`, `widgets/package_log.py` (create); `dev/accept/P2-I1/T05c.py`, `docs/reports/P2-I1/T05c.md` (create). Nav entries are supervisor glue.
- Acceptance: setup, `just check`, `uv run python dev/accept/P2-I1/T05c.py` (PASS no textual for both; path lines and compare on seed versions v1 and v2 with the moved marks; package summary; mount at 80 and 170; ends `T05c ok`). No pytest.
- Tests to add: none (T11 `test_path_screen.py`; package log joins it). Report <= 60 lines, deviations first, tui-layout checklist. Subject `P2-I1-T05c: ...`; trailer as T05a.
- Escalation: a needed fact absent from every view -> *Blocked*, never an extra call per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
