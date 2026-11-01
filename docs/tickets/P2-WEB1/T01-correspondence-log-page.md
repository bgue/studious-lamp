# P2-WEB1-T01 — correspondence log page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web, api
Depends on: S4 (merged)
Branch: `p2/web1-t01-correspondence-page`

## Goal
`GET /web/p/{project}/correspondence` shows the correspondence register in the log standard: the seven regions, the terminal's register columns, cells, panel and summary, the offered actions. One new module `tl_web/pages/correspondence.py`; `routers.PAGE_MODULES` already lists it. Register mode only (the terminal's triage inbox and clocks modes are not in this increment).

## Brief references (pasted)
> Columns, panels and summaries come from the same functions as the terminal (`correspondence_text.register_cells`, `item_page`, `summary_line`). Hidden = missing (ADR-0016): a hidden or unknown number is the one 404 page. `tl_web` imports terminal names only through `tl_web.present`, never `sqlalchemy`, `cur_*`, `tl_core` query modules or Textual.
> Terminal register (`tl_tui/widgets/correspondence_screen.py`, read only to compare): columns `REGISTER_COLUMNS`, drop order `REGISTER_DROP`, labels loaded with `("correspondence.Correspondence",)`, rows from `list_correspondence(project, state=None, sources=True, limit=500)`, key and record `(row.id)`, `(row.number, row.subject)`, summary `summary_line("register", len(rows))`. A row with `kind != "item"` (a transmittal) has no item to read.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/log.py
class WebLog[Row]:   # hooks to set: LOG_NAME, LABEL_TYPES, columns, drop_order, load_rows, row_key, row_record, row_cells, panel_text, summary_text
    @classmethod
    def page(cls, request: Request, project: str, *, q: str = "", sel: str = "", mode: str = "") -> Response: ...
def register(slug: str, cls: type[WebLog[Any]]) -> None: ...
# tl_web/webroute.py
def web_router() -> APIRouter: ...      # prefix /web, HTML failures
# tl_web/present.py re-exports: correspondence_text, plain_lines, as_client
# WebReadClient.list_correspondence(project, *, state=None, ..., sources=True, limit=500) -> list[RegisterLineView]
#   RegisterLineView: kind ("item"|"transmittal"), id, number, subject, state, ...
# WebReadClient.get_correspondence(project, number) -> ItemView
# tl_tui/correspondence_text.py
REGISTER_COLUMNS: tuple[str, ...]; REGISTER_DROP: tuple[str, ...]
def register_cells(line: RegisterLineView, labels: Labels | None = None) -> tuple[str, ...]: ...
def item_page(item: ItemView, suggestion: SuggestionView | None = None, labels: Labels | None = None, *, technical: bool = False, client: ClientInterface | None = None, project: str = "") -> Page: ...
def summary_line(mode: str, shown: int, *, closed_too: bool = False) -> str: ...
```
The model is the RFI page of `docs/reports/P2-WEB1/S4.md` ("Recipe for T15") and the docstring of `tl_web/log.py`. Panel for a transmittal row: the two plain lines `[f"{row.number}  {row.subject}", "Transmittal. Open it in the terminal for the full list."]`.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `docs/reports/P2-WEB1/S4.md` (the recipe)
- `packages/tl-tui/src/tl_tui/correspondence_text.py` (lines 32-66, 127-157, 203-211 only)
- `packages/tl-web/src/tl_web/log.py`
- `dev/accept/P2-WEB1/S4.py` (`PAGE_SOURCE` lines 82-136 as the shape of a page; `World`, `Doc`, `expect`, `passed`)
may explore: `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py` (`forge_item` signature only)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/correspondence.py` (create)
- `dev/accept/P2-WEB1/T01.py` (create)
- `docs/reports/P2-WEB1/T01.md` (create)

## Steps
1. Create `pages/correspondence.py`: `router = web_router()`, `CorrespondenceWebLog(WebLog[RegisterLineView])` (`LOG_NAME = "Correspondence register"`, `LABEL_TYPES = ("correspondence.Correspondence",)`), `register("correspondence", ...)`, and `GET /p/{project}/correspondence` (`q`, `sel`, `mode`). Type the row under `TYPE_CHECKING` only (do not add a dependency). A row of kind `item` gets `item_page(...)` with `client=present.as_client(self.client)`; any other kind gets the two-line transmittal text.
2. Write `dev/accept/P2-WEB1/T01.py`. Load S4 as a module and reuse its helpers:
   ```python
   spec = importlib.util.spec_from_file_location("accept_s4", ROOT / "dev/accept/P2-WEB1/S4.py")
   S4 = importlib.util.module_from_spec(spec); sys.modules["accept_s4"] = S4; spec.loader.exec_module(S4)
   S4.PAGE_SOURCE = "from fastapi import APIRouter\nrouter = APIRouter(prefix='/web', include_in_schema=False)\n"  # S4's demo RFI page off
   world = S4.World(Path(tmp))   # inside tempfile.TemporaryDirectory(); close world.backend in finally
   ```
   Add a second letter and a restricted one with `world.corr.forge_item(...)` (scope `S4.SCOPE`, restricted one with a secret word in its subject) before the first request. Checks (`PASS <letter>: ...`, exit 1 on the first failure): (a) `LOGS["correspondence"].SLUG == "correspondence"` and the router is mounted; (b) alice's page has the seven region ids in order, first headers Number, Subject, State, and each row's cells equal `correspondence_text.register_cells` for the same line (read with `world.reads("alice").list_correspondence(S4.PROJECT)`), constant columns dropped; (c) the panel of `P123-COR-0001` is `plain_lines(item_page(...))` of the same item; (d) `#log-status` equals `summary_line("register", n)`; (e) the restricted letter and its secret word are in no answer for alice, and its panel URL answers the same 404 bytes as `P123-COR-9999`; the controller (`ctl`) is not required to see it; (f) `?mode=technical`: plain for alice with `present.REFUSAL`, ids visible for `root`; (g) the filter `?q=` narrows the rows.

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T01.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0 (do not run `S4.py`: once T15 is merged its demo page collides with the real RFI page; T01.py switches that demo page off). Paste the last 10 lines of each in the report.

## Tests to add
None here. The tests piece (S5) writes `packages/tl-web/tests/test_web_correspondence_log.py` and the walk entries.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred). Commit subject `P2-WEB1-T01: <summary>`; no model names in any committed file. Do not discuss the commit trailer. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and report *Blocked* if a terminal function the page needs is reachable only through `widgets/*`, `log_screen` or `log_actions` (Textual), or if `WebReadClient` raises `UnsupportedRead` for a read the page needs (a missing read is S4's, not yours to add).
- Stop if the T01 script cannot construct `S4.World` (say what failed; do not edit `S4.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
