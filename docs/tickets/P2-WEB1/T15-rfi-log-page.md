# P2-WEB1-T15 — RFI log page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web, api
Depends on: S4 (merged)
Branch: `p2/web1-t15-rfi-page`

## Goal
`GET /web/p/{project}/rfis` shows the RFI log in the log standard: the seven regions, the terminal's columns, cells, panel and summary, the offered actions. One new module `tl_web/pages/rfis.py`; `routers.PAGE_MODULES` already lists it, so nothing else changes.

## Brief references (pasted)
> Columns, panels and summaries come from the same functions as the terminal (`rfi_text.rfi_cells`, `rfi_summary`, `rfi_lines`). Hidden = missing (ADR-0016): a hidden or unknown number is the one 404 page. `tl_web` imports terminal names only through `tl_web.present`, never `sqlalchemy`, `cur_*`, `tl_core` query modules or Textual.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/log.py
class WebLog[Row]:   # hooks to set: LOG_NAME, LABEL_TYPES, columns, drop_order, load_rows, row_key, row_record, row_cells, panel_text, summary_text
    @classmethod
    def page(cls, request: Request, project: str, *, q: str = "", sel: str = "", mode: str = "") -> Response: ...
def register(slug: str, cls: type[WebLog[Any]]) -> None: ...
# tl_web/webroute.py
def web_router() -> APIRouter: ...      # prefix /web, HTML failures
# tl_web/present.py re-exports: rfi_text, plain_lines, as_client
# WebReadClient.list_rfis(project, *, limit=500) -> RfiLog (.lines: RfiLogLine with .id .number .subject)
# WebReadClient.get_rfi(project, number) -> TechnicalView
```
The recipe, step by step, is in `docs/reports/P2-WEB1/S4.md` ("Recipe for T15") and in the docstring of `tl_web/log.py`; `dev/accept/P2-WEB1/S4.py` `PAGE_SOURCE` is a working copy of this exact page (copy it into the module, do not import from dev/).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `docs/reports/P2-WEB1/S4.md` (the recipe)
- `packages/tl-web/src/tl_web/log.py`
- `dev/accept/P2-WEB1/S4.py` (lines 82-136 `PAGE_SOURCE`; `World`, `Doc`, `expect`, `passed`)
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/rfis.py` (create)
- `dev/accept/P2-WEB1/T15.py` (create)
- `docs/reports/P2-WEB1/T15.md` (create)

## Steps
1. Create `pages/rfis.py`: `router = web_router()`, `RfiWebLog(WebLog[RfiLogLine])` as in the recipe, `register("rfis", RfiWebLog)`, and `GET /p/{project}/rfis` (`q`, `sel`, `mode` query strings). Type the row as `reports_technical.RfiLogLine` under `TYPE_CHECKING` only (do not add a dependency).
2. Write `dev/accept/P2-WEB1/T15.py`. Load S4 as a module and reuse its helpers, so the script stays short:
   ```python
   spec = importlib.util.spec_from_file_location("accept_s4", ROOT / "dev/accept/P2-WEB1/S4.py")
   S4 = importlib.util.module_from_spec(spec); sys.modules["accept_s4"] = S4; spec.loader.exec_module(S4)
   S4.PAGE_SOURCE = "from fastapi import APIRouter\nrouter = APIRouter(prefix='/web', include_in_schema=False)\n"  # S4's own demo page off
   world = S4.World(Path(tmp))   # inside tempfile.TemporaryDirectory(); close world.backend in finally
   ```
   Checks (one `PASS <letter>: ...` line each, `exit 1` on the first failure; S4's `passed`/`expect` do this): (a) `routers.page_routers()` includes the router of `tl_web.pages.rfis` and `LOGS["rfis"].SLUG == "rfis"`; (b) alice's page has the seven region ids in order, the first three headers are Number, Subject, State, and each row's cells equal `rfi_text.rfi_cells` for the same line (`S4.expected_rows`); (c) the panel route for `P123-RFI-0001` returns the terminal's `plain_lines(rfi_page(...))`; (d) the summary in `#log-status` equals `rfi_summary`; (e) the hidden RFIs (`P123-RFI-0004`, `-0005`) and their secret words are in no answer for alice; their panel URLs answer the same 404 bytes as `P123-RFI-9999`; (f) `?mode=technical` for alice keeps plain cells and shows `present.REFUSAL`, for `root` shows raw states; (g) a user with no cookie is redirected 303 to `/web/sign-in`.

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T15.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0 (do not run `S4.py` any more: its demo page registers the slug `rfis` that this page now owns; T15.py switches that demo page off). Paste the last 10 lines of each in the report.

## Tests to add
None here. The tests piece (S5) writes `packages/tl-web/tests/test_web_rfi_log.py` and the walk entries.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred). Commit subject `P2-WEB1-T15: <summary>`; no model names in any committed file. Do not discuss the commit trailer. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and report *Blocked* if a terminal function the page needs is reachable only through `widgets/*`, `log_screen` or `log_actions` (Textual), or if `WebReadClient` raises `UnsupportedRead` for a read the page needs (a missing read is S4's, not yours to add).
- Stop if the T15 script cannot construct `S4.World` (say what failed; do not edit `S4.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
