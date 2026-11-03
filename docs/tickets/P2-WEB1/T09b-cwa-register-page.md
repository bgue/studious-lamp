# P2-WEB1-T09b — CWA register page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T02, the awp reads seam (6cfcfb9), P2-I1 T05e (`cwa_text`, merged)
Branch: `p2/web1-t09b-cwa`

## Goal
`GET /web/p/{project}/cwas` shows the construction work areas in path order, in the log standard, with the terminal's columns, cells, panel and summary. One module, `tl_web/pages/cwas.py` (stub exists).

## Pins (this file wins; the common recipe is `docs/tickets/P2-WEB1/TWINS.md`)
1. `LOG_NAME = "CWA register"`, `columns = present.cwa_text.CWA_COLUMNS`, `drop_order = present.cwa_text.CWA_DROP`. Row type is the dataclass `CwaLine`: base `WebLog["present.cwa_text.CwaLine"]` (no `tl_tui` import).
2. `load_rows` makes three reads, once: `cwas = self.client.list_cwas(self.project)`; `path`: `self.client.get_path(self.project)`, where only a `record_not_found` means "no path yet" and gives `None` (`from tl_api.errors import body_for`; `mapped = body_for(exc)`; re-raise unless `mapped is not None and mapped[1].error == "record_not_found"`); `cwps = self.client.list_cwps(self.project)`. Rows: `lines = present.cwa_text.cwa_lines(cwas, path, cwps)`. **All areas are shown, retired ones too** (D32: the terminal hides them by default; a hidden row could not be found by the panel route). The retired state is in the panel's state line.
3. `row_key = row.row.id`; `row_record = (row.row.code, row.row.title)`; cells `present.cwa_text.cwa_cells(row)`.
4. Summary: `present.layout.join_facts(f"{n} CWAs", f"{r} retired" if r else "")` with `n = len(lines)`, `r` the retired count (`line.row.retired`). Keep in `self._summary`.
5. Panel (no read): `present.plain_lines(present.cwa_text.cwa_page(row, panel=True, technical=self.technical))`.

## Interfaces (verbatim from the tree)
```python
# tl_tui/cwa_text.py (re-exported as present.cwa_text)
CWA_COLUMNS; CWA_DROP; @dataclass(frozen=True) class CwaLine: row: CwaRow; position: int | None; cwps: tuple[CwpRow, ...]; steps: int
def cwa_lines(cwas, path: PathView | None, cwps) -> list[CwaLine]; def cwa_cells(line) -> tuple[str, ...]
def cwa_page(line: CwaLine, *, panel: bool = False, technical: bool = False) -> Page
# WebReadClient.list_cwas(project); .get_path(project, version=None) (404 when no path); .list_cwps(project)
# CwaRow: id code title location_text retired
```

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/cwa_text.py`, `packages/tl-tui/tests/fakes_awp.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/cwas.py` (replace the stub)
- `packages/tl-web/tests/test_web_cwa_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T09b rows`)
- `docs/reports/P2-WEB1/T09b.md` (create)

## Tests to add
`test_web_cwa_log.py`: cases (a)-(j) for slug `cwas` with the fake's 2 CWAs (A2 retired, listed) and 3 CWPs; positions come from path version 2; plus one case with `get_path` patched to raise the fake's `RecordNotFoundError` (every position `—`, page 200). Case (f) does not apply (the panel reads nothing): say so in the report; an unlisted code is the unknown-number 404 of (e). Screenshot `T09b-cwas.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of `T09b-cwas.png`.

## Escalation triggers
- *Blocked* if `cwa_text` needs a Textual import or a mirror raises `UnsupportedRead`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
