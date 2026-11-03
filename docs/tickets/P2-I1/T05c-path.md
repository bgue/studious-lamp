# P2-I1-T05c — Path of construction: Textual-free text module and screen

Status: ready after T05g merged (r10 re-spec; the first attempt stopped on facts the views lacked: D49-D50)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a (merged), T05g (`PathVersion.reason_code`)
Branch: `p2/i1-t05c-path` (reused)
Worktree: `/home/user/wt/i1/t05c` exists at the blocked attempt: run `git merge p2/i1` in it first (clean: the branch only holds the old blocked report, `docs/reports/P2-I1/T05c.md`; overwrite that file with the new report)

## Goal
A `LogScreen` (spec §8 "Path of construction", skill `tui-layout`) with its text in `tl_tui/path_text.py`, which does not import `textual` (D27); the web reuses it. No actions bar entries in I1: `actions_for` returns `[]`.

## Contract (fixed now; pure functions; PathView, PathStep, PathVersion, CwaRow, CwpRow from tl_mod_awp.views)
```python
# tl_tui/path_text.py
PATH_COLUMNS = ("Number","Subject","Reason","CWPs","Budget h"); PATH_RIGHT = ("Number","CWPs","Budget h")   # Number = position
@dataclass(frozen=True) class PathLine: step: PathStep; title: str | None; cwps: tuple[CwpRow, ...]
def path_lines(view: PathView, cwas: Sequence[CwaRow], cwps: Sequence[CwpRow]) -> list[PathLine]   # Subject "CWA code · name" ("code" alone when the area is unreadable); step.cwa None -> "—"
def path_cells(line: PathLine, labels: Labels | None = None) -> tuple[str, ...]                  # Reason = PathReason label of step.reason_code (humanize fallback), "—" when none; Budget h "—" when no CWP of the line has a budget
@dataclass(frozen=True) class Moved: cwa: str | None; before: int | None; after: int | None
def compare_versions(old: PathView, new: PathView) -> list[Moved]          # key v; mark(m) -> "↑2" (moved earlier), "↓1", "" unchanged, "new"/"gone"; rows in the new order, gone last
def compare_cells(m: Moved) -> tuple[str, ...]                             # CWA / Before / After / Change (the mark; CWA = code, "—" when None)
def version_heading(view: PathView) -> str                                 # "Path of construction · version 4"
def path_page(view: PathView, versions: Sequence[PathVersion], line: PathLine | None, *,
              previous: PathView | None = None, labels: Labels | None = None, panel: bool = False) -> Page
    # identity = version_heading. State line from the PathVersion row of view.version (recorded_at date, actor via display.actor_label, reason_code):
    #   version 1 "Defined 2026-10-01 by A. Ruiz"; later "Re-sequenced 2026-10-29 by A. Ruiz · reason Access" (" · reason ..." left out when reason_code is None).
    #   Reason text = labels.code_labels["PathReason"][code] or humanize(code) (same lookup as awp_text._discipline); no row for the version -> no state line.
    # sections, in order: "CWPs" (only when `line` is given: table Number/Subject/Budget h of line.cwps, "No CWPs in this area" when empty),
    #   "Steps changed" (only when `previous` is given: compare_cells rows of compare_versions(previous, view) whose mark is not "", "No steps changed" when none),
    #   "Versions" (table Version/Date/Who/Reason, newest first, current version marked "current" in a fifth column; Reason "—" when none)
```
Decisions (r10, answers to the first attempt's questions): `compare_versions` keys on the step's `cwa` code; steps with `cwa` None are left out of both sides. Budget h of a line = sum of its CWPs' `budget_hours` with `hours_text`; `—` when no CWP has a budget (none at all, or all null). Labels: the screen calls `load_labels(client, scope, ("awp.CWP",))` as `widgets/cwp_register.py:96` does; the standard code list `PathReason` arrives in `labels.code_labels["PathReason"]`. The screen loads the previous version for `previous` with one `get_path(project, version=view.version - 1)` when `view.version > 1` (a `RecordNotFoundError` -> `previous=None`, no status), never one call per row.
Keys: `[` and `]` previous/next version (client `get_path(project, version=)`), `v` toggles the log body between the steps and the compare rows of the previous version against this one (needs `view.version > 1`, else a status "No earlier version"), `F5` reload. Loads: `get_path`, `list_path_versions`, `list_cwas`, `list_cwps`. `KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  [ ] version  v compare  F5 reload  Esc back`.

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
`T05c.py` (Textual pilot on `FakeClient` + `seed_awp`, which holds path versions 1 and 2; v2 has `reason_code="Access"` since T05g): `PASS no textual` (import with `sys.modules["textual"] = None`); `PASS lines`; `PASS compare` (v1 against v2 with the moved marks `↑`, `↓`, `new`, `gone`); `PASS page` (state line for version 1 "Defined ..." and for v2 "Re-sequenced ... · reason Access"; sections CWPs, Steps changed, Versions in order); `PASS keys` (`[`, `]`, `v`); `PASS mount 80` and `PASS mount 170`; `PASS missing` (an error from `get_path` shows a status). Ends `T05c ok`.

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
