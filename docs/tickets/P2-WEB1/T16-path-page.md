# P2-WEB1-T16 — path of construction page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, the awp reads seam (6cfcfb9 and r8: `list_path_versions` mirror, `present.path_text`), P2-I1 T05c (`path_text`, merged)
Branch: `p2/web1-t16-path`

## Goal
`GET /web/p/{project}/path` shows one version of the path of construction (steps: Number = position, Subject, Reason, CWPs, Budget h) or its comparison with the version before, in the log standard, with the terminal's columns, cells, panel and summary. One module, `tl_web/pages/path.py` (stub exists).

## Pins (this file wins; the common recipe is `docs/tickets/P2-WEB1/TWINS.md`)
1. `LOG_NAME = "Path of construction"`, `LABEL_TYPES = ("awp.CWP",)` (as the terminal), no `drop_order`. Base `WebLog["present.path_text.PathLine | present.path_text.Moved"]` (quoted). Columns: `COMPARE_COLUMNS` when comparing, else `PATH_COLUMNS`.
2. Query strings, read from `self.request.query_params` (recipe 4): `?version=N` (ASCII digits, N >= 1; anything else is absent = the current one) and `?compare=1`.
3. `load_rows`, in this order, all through `self.client`: `view = get_path(project, version=N)`; `previous = get_path(project, version=view.version - 1)` only when `view.version > 1`; `versions = list_path_versions(project)`; `cwas = list_cwas(project)`; `cwps = list_cwps(project)`. Keep all five on `self`. A version that is not held (`?version=99`) is the one 404 page: do not catch it. Two catches only, each on `record_not_found` through `body_for` as `pages/cwas.py::_path` does: (a) `previous` (then None), (b) the first `get_path` when `?version=` is absent (a project with no path yet: no rows, empty summary, and the panel route is the 404 for any number).
4. Comparing happens only when `?compare=1` and `previous` is not None. Rows are then `present.path_text.compare_versions(previous, view)`, else `present.path_text.path_lines(view, cwas, cwps)`. `compare=1` with no earlier version shows the steps and the summary `No earlier version` (a constant `NO_EARLIER` of your own: the terminal's lives in a widget, which tl_web cannot import).
5. Summary as the terminal: steps `join_facts(f"{n} step(s)", f"version {view.version}")`; compare `join_facts(f"{n} row(s)", f"against version {previous.version}")` (`step` / `row` singular for 1). `n = len(rows)`, worked out in `load_rows`.
6. `row_record` must differ per row (the terminal's is constant and cannot be used): a step is `(str(step.position), subject)` with `subject = path_cells(line)[1]`; a comparison row is `(m.cwa or EMPTY, m.cwa or EMPTY)` (`EMPTY` = `present.text.EMPTY`). `row_cells` = `path_cells(line, self.labels)` or `compare_cells(m)`.
7. `row_key` is the id of the CWA in the `cwas` listing whose code the row names (a dict built in `load_rows`), else the same text as the row's number; so the Open link leads to the area's record page, as for the other twins. No actions (`actions_for` returns `[]`).
8. The panel must be of the same version and mode as the page: override `_panel_url(self, number)` to call `super()` and append `version=<view.version>` and, when comparing, `compare=1` (with `?` or `&` as the base string needs). `panel_text(row)`: `None` gives `["Nothing here."]`; else `present.plain_lines(present.path_text.path_page(view, versions, line, previous=previous, labels=self.labels, panel=True))`, where `line` is the row itself for a step, and for a comparison row the `PathLine` of `path_lines(view, cwas, cwps)` whose `step.cwa` equals `m.cwa` (None when there is none).
9. No navigation links in I1: the versions are reached by the URL; the panel's Versions table lists them. Do not add a template or CSS.

## Interfaces (verbatim from the tree)
```python
# tl_tui/path_text.py (re-exported as present.path_text)
PATH_COLUMNS; COMPARE_COLUMNS; PATH_RIGHT; PathLine(step, title, cwps); Moved(cwa, before, after)
def path_lines(view, cwas, cwps) -> list[PathLine]; def path_cells(line, labels=None) -> tuple[str, ...]
def compare_versions(old, new) -> list[Moved]; def compare_cells(m) -> tuple[str, ...]
def path_page(view, versions, line, *, previous=None, labels=None, panel=False) -> Page
# WebReadClient: get_path(project, version=None) -> PathView (404 if none); list_path_versions(project) -> list[PathVersion]; list_cwas; list_cwps
# PathView: id key title version current_version steps[position cwa reason_code actor recorded_at]
```

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`
- `packages/tl-web/src/tl_web/pages/cwas.py`, `packages/tl-web/tests/test_web_cwa_log.py` (models: the get_path catch, the fake loader)
- `packages/tl-tui/src/tl_tui/path_text.py`, `packages/tl-tui/src/tl_tui/widgets/path_screen.py` (the terminal's calls)
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-web/src/tl_web/log.py` (`_panel_url`, `row_for`), `packages/tl-tui/tests/fakes_awp.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/path.py` (replace the stub)
- `packages/tl-web/tests/test_web_path_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T16 rows`)
- `docs/reports/P2-WEB1/T16.md` (create)

## Tests to add
`test_web_path_log.py`: cases (a)-(h) and (j) for slug `path` with the fake (versions 1 and 2, 2 current; the world is P123). Case (i): the page has no technical-only row, so only the REFUSAL part applies (`bob`). Case (e): the number filter keeps one step; an unknown number is the 404. Case (f): no panel read exists, as for T09b; say so in the module docstring. Then: `?version=1` rows and status `... version 1` equal the text module's for version 1; `?compare=1` rows equal `compare_cells` of `compare_versions(v1, v2)`, the headers are `COMPARE_COLUMNS`, the status says `against version 1`; `?version=1&compare=1` shows the steps and `No earlier version`; `?version=0`, `abc`, `-1` are the current version, `?version=99` is the 404; the panel link in the page of `?version=1` holds `version=1` and that panel's lines equal `path_page` of version 1 (not the current one); same for the compare panel; the unpatched world: 200, empty table, any panel 404, `?version=1` 404. Screenshots `T16-path.png` and `T16-path-compare.png` (`?compare=1`).

## Acceptance
As TWINS.md (two `ls -l` of the PNGs). Commit subject `P2-WEB1-T16: ...`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead` or `path_text` needs a Textual import.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
