# P2-WEB1 twin tickets: the common recipe (T09, T09b, T10, T11, T16; M4 twins follow it)

A twin is a web page that shows the same words as a terminal screen. The words are the terminal's own
pure functions (`tl_tui/*_text.py`), reached only through `tl_web.present`; the reads are the mirror
methods of `tl_web.reads.WebReadClient` (the awp ones are in the tree). Model page:
`packages/tl-web/src/tl_web/pages/documents.py`; model test: `packages/tl-web/tests/test_web_document_log.py`.

## Page (the stub `pages/<slug>.py` already exists and is named in `PAGE_MODULES`; replace its body)
1. `router = web_router()` (keep the stub's). `class XWebLog(WebLog["Row"])`; row types come from `tl_mod_awp.views`
   under `if TYPE_CHECKING:` and the base is quoted. `tl_tui` is imported nowhere but `present.py`; a type that lives
   in a `tl_tui` text module is written `present.<module>.<Name>`.
2. Hooks: `LOG_NAME`, `columns`, `drop_order` (if the text module has one, else do not override), `load_rows`
   (reads through `self.client`, sets `self._summary`), `row_key` (the record id), `row_record` (`(number or code, title)`),
   `row_cells` (`self.technical` passes where the text function takes it), `panel_text` (`present.plain_lines(page)`),
   `actions_for` returning `[]` (no awp command has an `ACTION_UI` row; writes come with P2-I2), `summary_text` (`self._summary`).
3. `register("<slug>", XWebLog)` and `@router.get("/p/{project}/<slug>")` taking `request, project, q="", sel="", mode=""`
   and returning `XWebLog.page(request, project, q=q, sel=sel, mode=mode)`.
4. Extra query strings (`?depth=`, `?kind=`) are read inside `load_rows` from `self.request.query_params`; a bad value
   means "absent". The panel partial is asked without them, so a panel must still be found when the page was cut: filter
   rows in `load_rows` only by narrowing, never by hiding rows the unfiltered list would not have.
5. Hidden = missing (ADR-0016). Never catch a read's error to show other text or a fallback; a `RecordNotFoundError` from a
   read reaches `web_router`, which answers the one 404 page. The only read you may catch is stated in the ticket.
6. No `|safe`, no `sqlalchemy`, no `tl_core` runtime import (`test_web_imports.py` scans), no new template or CSS.
   A read or text function the page needs and does not have: stop, *Blocked* (do not add a query).

## Tests (one file `packages/tl-web/tests/test_web_<name>.py`, pytest on the S5 harness, no acceptance script)
Fixtures: `world` (module scope), `htmlkit`, `k` (see `conftest.py`); `world.web("bob")` is a plain user, `"boss"` an admin.
Data: the tl-tui fake of the awp reads, loaded by path (no sibling imports in importlib mode) and patched over the mirrors
with `mock.patch.object(WebReadClient, "<read>", lambda self, *a, **kw: fake.<read>(*a, **kw))` in a `fakes` fixture:
```python
REPO = Path(__file__).resolve().parents[3]
def load_fake():  # 3 CWPs, 2 CWAs (A2 retired), WBS 1 / 1.1 / 1.2, path v1 v2, one EWP, one PWP; project P123
    spec = importlib.util.spec_from_file_location("tl_web_tests_fakes_awp", REPO / "packages/tl-tui/tests/fakes_awp.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    fake = mod.FakeAwpSupport(); fake._init_awp(); mod.seed_awp(fake, "P123"); return fake
```
Cases, each as in `test_web_document_log.py` (copy its shape, drop its picture tests): (a) mounted and registered
(`routers.page_routers()`, `LOGS[slug].SLUG`); (b) `doc.regions() == list(htmlkit.LOG_REGIONS)`, headers, and every
row's cells equal the text module's cells (`htmlkit.project_cells`); (c) the panel's `pre()` lines equal
`present.plain_lines(<page>(..., panel=True))`; (d) the status line equals the summary; (e) `?q=` keeps only the matching
row and an unknown number is a 404 with the same bytes as another unknown number; (f) a read that raises
`RecordNotFoundError` (patch one read of one listed row) is the same 404 bytes (hidden = missing); (g) no cookie is a 303
to `/web/sign-in`; (h) `doc.buttons() == []` and `#log-actions` holds only the Open link; (i) plain versus technical:
`bob` with `?mode=technical` gets `present.REFUSAL` as status and the plain panel; `boss` with `?mode=technical` has the
technical lines (record id) that the plain panel lacks (skip (i) where the page has no technical row; say so in the report).
(j) the page also answers on the real, unpatched world (no fakes): 200, empty table, 404 for any panel.
**Walk row.** Add the ticket's `WALK` entry in `packages/tl-web/tests/walk.py` under its own marker line (never another's):
`("GET", "/web/p/{project}/<slug>"): Row("<kinds of text the page carries>", _page("<slug>")),`.
**Screenshot** (owner asked). Copy `shoot` and `SHOTS` unchanged from `docs/tickets/P2-WEB1/provided/shot_recipe.py`
into the test file; one test, with the `fakes` fixture on, calls `shoot(world.app, world.web("bob").token, "/web/p/P123/<slug>",
"<id>-<slug>.png")` and asserts the file exists. PNGs go to `/home/user/wt/p2-web1/.accept/shots` (ignored by git; do not
`git add` them). If `node` or Chromium is missing, stop, *Blocked*. After the test passes, `ls -l` the PNG(s) in the report.

## Acceptance (once; do not run `just gate`, the gate runner does)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest packages/tl-web/tests/<your test file> packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_plain_walk.py packages/tl-web/tests/test_web_imports.py -q
```
Paste the last 5 lines of each. Report `docs/reports/P2-WEB1/<id>.md`, at most 60 lines, deviations first. Commit subject
`P2-WEB1-<id>: <summary>`, no model names in any file; end the message with the attribution trailer the harness requires,
then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer.
