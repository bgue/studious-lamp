# P2-FORMS-WEB W2 — The fill page and the `/web/forms` mount

kind: piece
review: full
branch: p2/forms-w2-fill-page
worktree: /home/user/wt/forms/w2
Status: staged, **not dispatchable until** W1, B1, T04 and S3 are merged and P2-X4 is on `p2/ip` (the page reads through routes that exist only through the X4 hooks). It does not run in the round of S6 (both edit `tl_web/app.py`; the orchestrator staggers).
Depends on: W1 (vendored renderer and `dev/tools/surveyjs_probe`), **B1** (`tl_core/forms/surveyjs.py`, `to_surveyjs(fields, fmt)`: an implementer ticket after W1 and T01; the page gets its model from it), S3 (commands), T04 (read routes; X4 C2: the hooks).
Gated: security (a page that renders template text into a script-bearing page, and a web write path for answers; the owner approves, APPROVALS line). Labels: web, security. Heavy runs: at most 2 at once.

## Why
`forms-eval.md` §2.5, §3, §8.3 (W2) and ADR-0031 decisions 11, 13. A signed-in person fills a general form, or the form bound to a record (an inspection reached from a scanned card), in a browser. The terminal and the CLI (T05, T07) already fill forms; the page is the phone surface.
The server stays the validator (`validate_answers` in the command handler); the browser model only helps the person. Hidden looks exactly like missing; a draft is its author's alone.

## Decisions this spec makes (record in the report and in `packages/tl-web/README.md`)
- **D27 how the page reads (written against the X4 hooks, read `git show p2/x4:tests/ext_demo/src/tl_mod_ext_demo/{module,routes}.py` and `git show p2/x4:packages/tl-core/src/tl_core/modules.py` lines 183-345).** Forms names its hooks in its own package only (`forms` is not in `IN_TREE_SURFACES`): T04 declares
  `read_routers=("tl_mod_forms.routes:router",)`; T05 `cli_groups=("tl_mod_forms.cli:app",)`; T06 `tools=("tl_mod_forms.tools:register",)` (names are T04-T06's to fix; W2 reads whatever T04 merged). The page reads through `WebReadClient` methods that call T04's route functions (the rule of
  `tl_web/reads.py`: a page shows nothing the JSON route would not); W2 adds the `WebReadClient` rows and their `MIRRORS` entries, not a query. If T04's route names differ from the table below, W2 follows T04.
- **D28 routes** (all under `/web/forms`, router `tl_web/pages/forms.py` added to `PAGE_MODULES` by name; the one edit of `tl_web/app.py` or `routers.py` this piece may make is that name):
  | Route | Does |
  |---|---|
  | `GET /web/forms` | the published general templates the viewer may fill (title, key, version), nothing else |
  | `GET /web/forms/t/{template_id}` | the fill page for a general template |
  | `GET /web/forms/for/{key}` | the fill page for the form bound to a record (inspection checklist now, permit later; `form_for(record)` through T04's `/forms/for/{key}`); a record with no bound template, a hidden record and an absent key answer the one 404 page |
  | `POST /web/forms/t/{template_id}/draft` | `SaveFormDraft` (`draft_id` from the hidden field), CSRF, as the signed-in person; answers back as a status line and the draft id |
  | `POST /web/forms/t/{template_id}/submit` | `SubmitForm`; success redirects 303 to a plain "received" page `GET /web/forms/done/{key}` that shows the key and nothing else |
  | `POST /web/forms/for/{key}/submit` | the typed command of the binding (T04 names it in the `form_for` payload) as the person |
  Writes run `tl_api.commands.run_command` exactly as `tl_web/actions.py` does (the one access check; CSRF `csrf.verify` as router dependency; the command stamped with actor, scope and source `web`); a refusal is the status line `! <message>` and nothing else; no answer value is ever in a status line or a log.
- **D29 the page is two files and a data block.** Template (`templates/forms/fill.html`): the form chrome, a `<noscript>` paragraph ("this page needs a script; use the terminal or ask for a paper copy"), a `<div id="survey">`, hidden fields (`csrf`, `draft_id`, `answers_json`), the `<link>` and `<script src>` of the three vendored files (core first, then the renderer) and `static/forms.js`; and **one**
  `<script type="application/json" id="form-model">` data block holding `to_surveyjs(...)` output (B1; the model sets `clearInvisibleValues: onHidden`, and `surveyjs_unsupported(fields)` ids, today the photo fields, are shown as a plain line under the form: "these questions need the terminal: <texts>", escaped by the template) serialised with Jinja's `tojson` (it escapes `<`, `>`, `&`, `'`; a test proves `</script>` and `<!--` in a title, help text or choice cannot end the block). `static/forms.js` (about 80 lines, no `eval`, no `innerHTML`, no inline handler): reads the block, builds `new SurveyUI.Model(model)` (the renderer class is `SurveyUI.Model`; `SurveyUI.Survey` is undefined in the vendored 3.2.5 build, W1 report; a test greps `forms.js` for `SurveyUI.Survey(`),
  sets `survey.data` from `answers_json` (draft resume is B3; here only the field exists and is read), maps survey data to the answers list `[{q, value}]` (format 2; `[{q, value, note}]` for format 1) on "Save draft" and on complete, writes it to `answers_json` and submits the real `<form>` (so the server and the CSRF check do the work).
  The renderer must never get markup from a template: set `survey.textMarkdown`/`onTextMarkdown` to nothing (plain text only) and `survey.mode = "edit"`; a test renders a template whose title, field text, help and choices are `<img src=x onerror=...>` and asserts the DOM (probe) shows them as text.
- **D30 policy unchanged.** The page works under the web client's CSP (no `unsafe-inline`, no `unsafe-eval`); the probe of W1 is extended by a clause that loads the real page. A new header is not needed. If the renderer needs a relaxation, stop with `122`.
- **D31 hidden-looks-missing and drafts.** The routes pass the viewer's identity through `WebReadClient` and the command door; they never read a record directly. The author-only draft rule is CR1's and is exercised, not re-implemented: a `draft_id` of another author answers the same status line as an absent one.

## Goal
`tl_web/pages/forms.py` (router, the six routes), `tl_web/templates/forms/{fill.html,list.html,done.html}`, `tl_web/static/forms.js` and `forms.css` (own, small; a tone class for the status line is reused from `tl.css`), `WebReadClient` rows, `tests`, docs. The page of a bound form shows the record key and the template title; the page of a general form shows the title and a template version.
Typed forms (an inspection) post to the typed command named by the binding payload; until S3s merges, `for/{key}` answers 404 for every key (the binding list is empty) and a test proves exactly that (the first real binding is S3s' test).

## Allowed paths
- `packages/tl-web/src/tl_web/pages/forms.py` (create), `.../templates/forms/*` (create), `.../static/forms.js`, `.../static/forms.css` (create), `.../routers.py` (one name in `PAGE_MODULES`), `.../reads.py` (rows and `MIRRORS` entries)
- `dev/tools/surveyjs_probe/**` (extend with the page clause)
- `packages/tl-web/tests/test_web_forms_*.py` (create), pinned web lists named in the report with old and new count (`test_web_imports.py`, a route table pin)
- `packages/tl-web/README.md` (D27 to D31, the route table), `docs/reports/P2-FORMS/W2.md` (create)
Not allowed: `tl_api/app.py`, `tl_api/auth.py` (S6's), the vendored files (W1), `tl_core/**`, `tl_mod_forms/**`, `schema/**`, any other module's page, a new dependency.

## Tests to add
Lint-clean (`ruff format`, `ruff check`, strict `pyright`); no sleeps; no network. Use the `light_world` and `htmlkit` fixtures of `packages/tl-web/tests`.
- `test_web_forms_pages.py`: list shows only published general templates; fill page for a general template has the form model block, the three script and style references, `forms.js`, the hidden fields, a `<noscript>` line; no inline script other than the JSON block, no `on*` attribute, no ` style=`; the standard `/web` headers.
- `test_web_forms_model_block.py`: a template whose texts hold `</script><script>alert(1)</script>`, `<!--`, ` `, `"` and `'` renders a block that parses as JSON equal to the model and that no HTML parser ends early (parse with `htmlkit`).
- `test_web_forms_write.py`: draft and submit as the signed-in person create the events of S3 (use the world helpers), source `web`; a missing or wrong CSRF token is refused before anything runs; a person without `forms.submit` gets the status line and no event; an agent token gets the closed guard's answer; a draft of another author, a hidden bound record and an absent key answer **identical** 404 or status text; no answer value appears in any response other than the person's own form re-render on a refusal that echoes nothing (assert it echoes none).
- `test_web_forms_confidentiality_walk.py`: five readers over `/web/forms`, `/web/forms/t/{id}`, `/web/forms/for/{key}`, `/web/forms/done/{key}`: hidden looks like missing, byte for byte (status, headers that matter, body), count of list rows included.
- `test_web_forms_bound_empty.py`: `for/{key}` is 404 for every key while no source is registered.
- `dev/tools/surveyjs_probe` page clause: the real fill page (served by the test app on an ephemeral port, signed in with a test session) renders, one answer is typed through the DOM, "Save draft" and submit post, no CSP violation. Run once by the builder; output in the report.

## Gate
`just check`; then one run at a time: 1. `just gate packages/tl-web/tests/test_web_forms_pages.py packages/tl-web/tests/test_web_forms_model_block.py packages/tl-web/tests/test_web_forms_bound_empty.py`; 2. `just gate packages/tl-web/tests/test_web_forms_write.py packages/tl-web/tests/test_web_forms_confidentiality_walk.py`;
3. `just gate packages/tl-web/tests/test_web_headers.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_actions.py packages/tl-web/tests/test_web_confidentiality_walk.py`; `just gate-pg` on the write test; then the probe.

## Mutation cap
One sentinel plus at most 5 targeted: the model block serialised without `tojson` escaping; CSRF dependency removed from the submit route; a hidden bound record answers a different status; `survey.textMarkdown` left at the library default in `forms.js` (the DOM test must fail); `answers_json` trusted without the command's own validation (a test posts an out-of-range value and the status line must refuse). 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; first line deviations or none. Include: the final route table, how T04's routes were read, the probe output, pinned files with old and new count. Commit `P2-FORMS-W2: ...` with the session trailers; no model names in committed text.
