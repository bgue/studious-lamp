# P2-WEB1-T11 — External packages (EWP and PWP) page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T02, the awp reads seam (6cfcfb9), P2-I1 T05f (`package_text`, merged)
Branch: `p2/web1-t11-packages`

## Goal
`GET /web/p/{project}/packages` shows the EWP and PWP references of a project in the log standard, with the terminal's columns, cells, panel and summary, and the `?kind=EWP|PWP` and `?constraints=1` filters. One module, `tl_web/pages/packages.py` (stub exists).

## Pins (this file wins; the common recipe is `docs/tickets/P2-WEB1/TWINS.md`)
1. `LOG_NAME = "Packages"`, `columns = present.package_text.PACKAGE_COLUMNS` (no drop order). Row `PackageRow`, base `WebLog["PackageRow"]`.
2. `load_rows`: one read `everything = self.client.list_packages(self.project)`; `kind` from `?kind=` (only `EWP` or `PWP`, else `None`), `constraints_only` from `?constraints=1`. Rows: those of `everything` with `kind` and `row.constraint_source` as asked. `row_key = row.id`; `row_record = (row.package_no, row.title)`; cells `present.package_text.package_cells(row)`.
3. Summary: `present.package_text.summary_line(len(rows), len(everything), kind=kind, constraints_only=constraints_only, text="")`.
4. Panel (no read): `present.plain_lines(present.package_text.package_page(row, panel=True, technical=self.technical))`.

## Interfaces (verbatim from the tree)
```python
# tl_tui/package_text.py (re-exported as present.package_text)
PACKAGE_COLUMNS; def package_cells(row) -> tuple[str, ...]; def package_page(row, *, panel=False, technical=False) -> Page
def summary_line(shown_rows, total, *, kind, constraints_only, text) -> str
# WebReadClient.list_packages(project, *, kind=None) -> list[PackageRow]
# PackageRow: id kind package_no status_text forecast_date actual_date constraint_source source_system title cwps
```

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/package_text.py`, `packages/tl-tui/tests/fakes_awp.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/packages.py` (replace the stub)
- `packages/tl-web/tests/test_web_package_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T11 rows`)
- `docs/reports/P2-WEB1/T11.md` (create)

## Tests to add
`test_web_package_log.py`: cases (a)-(j) for slug `packages` with the fake's one EWP and one PWP; `?kind=PWP` leaves the PWP and the status line names it (`summary_line(1, 2, kind="PWP", ...)`); `?kind=xyz` is ignored; `?constraints=1` equals the constraint sources only. Case (f) does not apply (the panel reads nothing): say so. Screenshot `T11-packages.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of `T11-packages.png`.

## Escalation triggers
- *Blocked* if `package_text` needs a Textual import or a mirror raises `UnsupportedRead`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
