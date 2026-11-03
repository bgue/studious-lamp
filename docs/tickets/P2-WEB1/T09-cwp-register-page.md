# P2-WEB1-T09 — CWP register page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T02, the awp reads seam (6cfcfb9), P2-I1 T05a/T05d (`awp_text`, merged)
Branch: `p2/web1-t09-cwp`

## Goal
`GET /web/p/{project}/cwps` shows the CWP register in the log standard: the terminal's columns, cells, panel and summary. One module, `tl_web/pages/cwps.py` (stub exists). (The CWA register is T09b.)

## Pins (this file wins; the common recipe is `docs/tickets/P2-WEB1/TWINS.md`)
1. `LOG_NAME = "CWPs"`, `LABEL_TYPES = ("awp.CWP",)`, `columns = present.awp_text.CWP_COLUMNS`, `drop_order = present.awp_text.CWP_DROP`. Row type `CwpRow` (`tl_mod_awp.views`), base `WebLog["CwpRow"]`.
2. `load_rows`: `self.client.list_cwps(self.project)` (no filters; `?q=` is the page's own text filter, which also finds a state, discipline or CWA, D31). `row_key = row.id`; `row_record = (row.number, row.title)`; cells `present.awp_text.cwp_cells(row, self.labels)`.
3. Summary (the terminal builds it inside its screen, so it is pinned here): `f"{n} CWP"` plus `"s"` when `n != 1`, `n = len(rows)`; keep in `self._summary`.
4. Panel: `full = self.client.get_cwp(self.project, row.number)` (one read per request; no cache needed) and `present.plain_lines(present.awp_text.cwp_page(full, self.labels, technical=self.technical, panel=True))`. A `RecordNotFoundError` is not caught (recipe 5).
5. The terminal's `d`, `s`, `c` keys (discipline, state, group by CWA) are not in this increment; the report says so.

## Interfaces (verbatim from the tree)
```python
# tl_tui/awp_text.py (re-exported as present.awp_text)
CWP_COLUMNS: tuple[str, ...]; CWP_DROP: tuple[str, ...]
def cwp_cells(row: CwpRow, labels: Labels | None = None) -> tuple[str, ...]
def cwp_page(d: CwpDetailView, labels: Labels | None = None, *, technical: bool = False, panel: bool = False) -> Page
# WebReadClient.list_cwps(project, **filters) -> list[CwpRow]; .get_cwp(project, number) -> CwpDetailView
# CwpRow: id number title state discipline cwa planned_start planned_finish budget_hours allocated
```

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md` (the recipe, tests, screenshot, acceptance)
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/awp_text.py`, `packages/tl-tui/tests/fakes_awp.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/cwps.py` (replace the stub)
- `packages/tl-web/tests/test_web_cwp_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T09 rows`)
- `docs/reports/P2-WEB1/T09.md` (create)

## Tests to add
`test_web_cwp_log.py`: cases (a)-(j) of the recipe for slug `cwps`, with the fake's 3 CWPs; the panel of one CWP equals `cwp_page(fake.get_cwp("P123", n), labels, technical=False, panel=True)` lines; screenshot `T09-cwps.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of `T09-cwps.png`.

## Escalation triggers
- *Blocked* if `awp_text` needs a Textual import, if a mirror raises `UnsupportedRead`, or if the unpatched world cannot answer an awp read (say the error).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
