# P2-I3-T06c — item_text.py and ItemLibraryScreen (the company item library)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06a (merged), T04b (merged), S5 (merged), T06d (merged; the freshest precedent)
Branch: `p2/i3-t06c-item-library`

## Goal
The item library as a Textual-free text module plus a read-only `LogScreen`, unregistered. The owner sees it in the acceptance screenshots (`.accept/shots/T06c-items-<w>.svg`).

## Brief references (pasted)
> Contract: `docs/tickets/P2-I3/text-contracts.md` "Shape every module follows", "Items (`item_text`)" and "Screens". Layout rules: skill `tui-layout` (identity line, summary, named sections, `—` in fixed sections, table drops its least-needed column first).
> Columns `ITEM_COLUMNS = ("Number", "Subject", "State", "Category", "UOM", "Projects")`; Number = `code`, Subject = `title`, State = `Active` or `Retired` (`retired`), Category = word, UOM = `unit_label(base_uom)`, Projects = `item.projects` as text.
> `ITEM_DROP = ("Projects", "UOM", "Category")` (least needed first); `RIGHT = frozenset({"Projects"})`. `columns_for(rows)` drops Category, UOM, Projects, State when every row has the same value (State, Number, Subject stay first when varying; Number and Subject never drop).
> Category word: `code_label(labels, "ItemCategory", code)` when `labels` knows it, else `humanize(code)` (`pipe` becomes `Pipe`); `labels=None` allowed.
> Keys text `ITEM_KEYS = "r state  / filter  F5 reload  Esc close"`; `next_state(current)` cycles `None` (all), `"Active"`, `"Retired"`, then back; pure. `summary_line(shown, total, *, state=None, project=None, text="")` reads `Showing 12 of 50 items` plus `· Active`, `· project P123`, `· filter "x"` only when set.
> `item_page(item, projects, labels=None, *, technical=False) -> Page`: identity `code · title`; state `Active`/`Retired`; summary `<Category> · <UOM> · used in N projects` (N = `len(projects)`; `1 project` singular); section Specification (property lines Size, Rating, Material, Consumable `Yes`/`No`; `—` when empty; `technical` adds Id) and section Projects (table `Project, On hand, Reserved, Available` from `ItemProjectView` with `qty_text`; note `Not used in any project`). `item_lines(item, projects, labels=None, *, technical=False, width=None) -> list[str]` is `plain_lines`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_mod_materials.views.MaterialItemView: id code title category base_uom size_text rating_text material_code consumable retired projects(int)
# tl_mod_materials.views_detail.ItemProjectView: project title(=project id) on_hand reserved available (Decimal) uom
# ClientInterface: list_materials_items(self, *, project: str | None = None, limit: int = 1000) -> list[MaterialItemView]
#                  list_materials_item_projects(self, code: str) -> list[ItemProjectView]
# tl_tui.materials_text: qty_text(Decimal) -> str   day(iso) -> str
# tl_tui.layout: EMPTY Page Prop Section TableRow identity_line join_facts plain_lines prop shown(as _shown) Panel render
# tl_tui.display: Labels code_label humanize mode_of    tl_tui.text: unit_label
# shape to copy: tl_tui/mto_text.py (columns_for row_cells summary_line mto_page mto_lines) and widgets/mto_screen.py (whole; read-only LogScreen over MtoLineView)
```
`ItemLibraryScreen(client: ClientInterface, project: str | None = None)` in `widgets/item_library.py`: `LOG_NAME` "Items", `KEY_HINTS` = `ITEM_KEYS`, `KEY_CELLS` ("r state", "/ filter"), `BINDINGS` for `r` (does nothing while `isinstance(self.focused, Input)`), `drop_order` = `ITEM_DROP`, `keep_columns` = Number, Subject, State.
`load_rows`: `list_materials_items(project=self.project, limit=MAX_VIEW_ROWS)` (`from tl_mod_materials.limits import MAX_VIEW_ROWS`), keep what was read in `self.views` (the summary total) and return from `load_rows` only the rows passing the `r` state filter (client side; `r` calls `self.reload()`). `panel_text`: `list_materials_item_projects(row.code)`; a `CLIENT_ERRORS` error gives `Projects could not be read.` as an empty list and an error line via `self.say`. `log_project()` returns `self.project or ""`: check what the breadcrumb does with an empty string; if the frame cannot show a company-level log, stop and report Blocked.
`row_key` = `row.code`; `row_record` = `(row.code, row.title)`; `actions_for` returns `[]`; `open_row` does nothing.

## Context (read these, nothing else)
- `docs/tickets/P2-I3/text-contracts.md`, `packages/tl-tui/src/tl_tui/mto_text.py` and `packages/tl-tui/src/tl_tui/widgets/mto_screen.py` (whole; the shape)
- `dev/accept/P2-I3/T06d.py` (whole: seed copy, `EmbeddedClient`, `TlApp` host, `settle`, `screen_text`, screenshot save; copy its helpers)
may explore: `widgets/log_screen.py`, `layout.py`, `display.py` lines 70-104

## Allowed paths
- `packages/tl-tui/src/tl_tui/item_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/item_library.py` (create)
- `dev/accept/P2-I3/T06c.py` (create), `docs/reports/P2-I3/T06c.md` (create)
Not here: `materials_text.py`, `app.py`, `client.py`, `log_screen.py`, `layout.py`, any test file.

## Acceptance
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06c.py
```
`T06c.py` (you write it; exit 0; one `PASS <check>` per line): (1) text, over a temp copy of the seed ledger (50 items): for widths 80 and 170 print `item_lines(...)` of the first item and the first rows as joined cells; assert no `None`, no standalone `-`, `—` for an empty Size,
sections in the order Specification, Projects, every table line within the width, the `Not used in any project` note on a hand-built item with no projects, `Consumable` reads `Yes` or `No`, `columns_for` drops State when no item is retired, `next_state` cycles None, Active, Retired, None; `import tl_tui.item_text` leaves `textual` out of `sys.modules` (fresh subprocess).
(2) screen: push `ItemLibraryScreen(client)` and `ItemLibraryScreen(client, "P123")` on `TlApp` at (80, 30) and (170, 40); `screen_text` shows an item code and the keys row; `down` shows the panel with `Specification`; `r` changes the summary to name `Active`; Esc closes; save
`app.export_screenshot(title="Items")` to `.accept/shots/T06c-items-<w>.svg` (company-level, 80 and 170) and `T06c-items-P123-<w>.svg` (project, 170 only).

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, each command with <= 5 decisive output lines; list the screenshot paths. Commit subjects `P2-I3-T06c: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file. Do not run pytest.

## Escalation triggers
- Stop and report *Blocked* if the frame cannot show a log without a project, if a contract line needs `textual` in the text module, or if a name listed under Interfaces is missing.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
