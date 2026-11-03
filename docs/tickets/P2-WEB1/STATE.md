# P2-WEB1 STATE  r=7 base=c9a2b23 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-web1
## BOARD
S1 p mrg f 3145932 foundation; F1 csrf catch-all fixed; deviations ratified
S2 p mrg f 3145932 run_command + action_ui (merge 773f38c)
T06 t mrg l 3145932 licence check; blk was subject prefix only
S3 p mrg f 26708be page1 route + web mirrors; argv pin ratified (merge 0274a26)
S4 p mrg f 8fb6905 reads, WebLog, /do; ~1,160 line overrun accepted
T15 t mrg f 88ddfe7 RFI log page (merge a2f0a1d)
T01 t mrg f 86b4338 correspondence register; transmittal rows no actions (359a3e6)
T05 t mrg f 9e5e1b3 PDF viewer page, pdfview.js (merge 0ca0d5f)
T02 t mrg f 567ed55 document log page (merge e16b5bd)
S6 p mrg f 70f45e4 record screen, Details Properties History (merge 54d80da)
T03 t mrg f 14f0536 Links + Trace tabs (merge 9de8bac)
T04 t mrg f 979699a Thread + Files tabs (merge d8c8e45)
S5 p mrg f 230e2ae tests piece, 338 tests; +500 headers fix (merge c89e9bc)
T08 t mrg l 250a7d3 demo script P2-WEB1.sh, sqlite+postgres 5/5 (merge fb0c930)
SECFIX p mrg f b817341 F1 login CSRF, F2 guard default-on, F3 rate-limit tests (merge 0118cb0)
T07 t todo l - docs: tl-web README, runbook web-client, AGENTS row; r8 after twins merge
T09 t stg f - CWP register page, ticket T09-cwp-register-page.md, ready, branch p2/web1-t09-cwp
T09b t stg f - CWA register page, T09b-cwa-register-page.md, ready, branch p2/web1-t09b-cwa
T10 t stg f - WBS tree page only, T10-wbs-tree-page.md, ready, branch p2/web1-t10-wbs
T11 t stg f - packages page, T11-external-packages-page.md, ready, branch p2/web1-t11-packages
T16 t todo f - path page; staged, waits P2-I1 T05c path_text, then list_path_versions seam
T12-T14 t todo f - M4 twins (stock+movement; receipt+MTO; items+locations); wait for M4 screens (p2/i3)
## DEC
D1 2026-11-01 owner: tests deferred; every item leaves dev/accept/P2-WEB1/<id>.py; S5 writes the spec 11 "Tests added" files plus tests/tools/test_check_licences_vendored.py
D2 2026-11-01 file ids: S1..S4 as spec, S5 = tests, T01..T08 = spec T1..T8, T09..T14 = twins; reports docs/reports/P2-WEB1/<id>.md
D3 2026-11-01 spec S2 split: run_command + action_ui stay in S2 (independent of S1, runs r1); tl_web/actions.py and POST /do route move to S4; the offered-now guard and its mutant move to S4 (still a Sec row)
D4 2026-11-01 manifest = static/vendor/VENDORED.toml, [[file]] with path,name,version,licence,url,sha256; T06 independent of S1 (format pasted in both)
D5 2026-11-01 S1 pins: cookie resolving to an agent principal is 401; all /web routes include_in_schema=False so openapi.json is unchanged by S1
D6 2026-11-01 TL_WEB=on with tl_web missing = start error; unset (default on in dev/test/ci) with it missing = silent
D7 2026-11-01 S1 vendors htmx and pdf.js together (T05 never touches vendor); licence recorded as the upstream LICENSE says (htmx 2.x may be 0BSD, not BSD-2-Clause as spec 2); non-permissive = stop, 95
D8 2026-11-01 only 5 pieces (S1-S5): RFI page may become a Haiku ticket after S4's core is in the tree (decide r2)
D9 2026-11-01 Q1 answered: RFI page = Haiku ticket T15 after S4 (interfaces in tree, 3 files, recipe in S4 report); S4 proves WebLog with an in-script page
D10 2026-11-01 seam: tl_web/routers.py PAGE_MODULES (find_spec skip) mounts page routers before the 404 catch-all; pieces never edit app.py or routers.py (my 4 lines in app.py, 4d666fc)
D11 2026-11-01 HTML error path = tl_web/webroute.py WebRoute/web_router() (S4); S3 mirrors pass JSON errors through (bytes endpoints, no HTML)
D12 2026-11-01 BODY_LIMITS row ("/web/", 64 KiB) after /web/sign-in goes to S4 (answers S1 open question); TL_WEB bad value = start error accepted
D13 2026-11-01 every spec: setup line (uv sync --all-packages + NODE_OPTIONS) and commit subject P2-WEB1-<id>: ; S3 acceptance has a pytest regression sniff of existing tl-tui preview tests (move only)
D14 2026-11-01 S4 overrun accepted; F1 source stays "tui" as stamp writes (no new event source without a schema decision); one argv assertion in tl-tui preview test ratified (S3)
D15 2026-11-01 supervisor seam r3: WebReadClient.file_info + MIRRORS row file_info->get_file_info (5 lines, reads.py), because T05 needs size and type; S5 mirror test counts it
D16 2026-11-01 T03/T04 fail 01-tiers 6 (items 1,2,5): record header, badges, properties and history logic lives in Textual widgets (record_view.py 521 lines, psets_tab, trace_tab), not in pure modules. r4: read those, then either one builder piece S6 (record screen, T03+T04 by coherence, rule 12) or a pure-module split that passes 6
D17 2026-11-01 once T15 merges, dev/accept/P2-WEB1/S4.py cannot run (its demo page collides with the real slug rfis); T15/T01 scripts load S4.World with S4.PAGE_SOURCE replaced by an empty router; S5 replaces S4.py checks with tests
D18 2026-11-01 r4 supervisor seams (17 diff lines + 2): WebLog.panel_image(row)->str hook (default "") shown by panel_body.html above the panel text, .tl-panel-img rule in tl.css (7c0544d); present re-exports file_text (17e12bf). Both for T02
D19 2026-11-01 Q3 closed (orch approved S6). S6 cut: builder moves record_view/psets_tab/links_tab/trace_tab logic into 4 Textual-free tl_tui modules (record_text, properties_text, links_text, trace_text; old names re-exported, no test edited), adds mirrors conformance + trace, action_views helper in log.py, pages/record.py frame with Details, Properties, History and a lazy tab registry (TAB_MODULES record_links/trace/thread/files). Links, Trace, Thread, Files tabs become Haiku tickets T03 (links+trace) and T04 (thread+files) after S6 merges, one tab module + template each
D20 2026-11-01 documents web log has no actions in i1: no document command has an ACTION_UI row (terminal builds them inside its screen); T02 overrides actions_for to []. Issue/supersede/void revision and transmittals stay terminal-only; follow-up for the Phase 2 plan, not this increment
D21 2026-11-01 S6 acceptance carries one pytest line (existing tl-tui record/psets/links/trace tests, move-only regression sniff, as D13 did for S3); new tests stay deferred to S5. Orchestrator may strike the line; then the move is checked by the script only
D22 2026-11-01 T01 open point left as built: status line counts all loaded rows, the terminal counts the filtered rows; S5 pins the web behaviour; revisit at DONE if the owner wants parity
D23 2026-11-02 r5 seams (3 code lines + 1 moved): links_text.COLUMNS (moved from widgets/links_tab, imported back), present.thread_text. S6.py nav-order and `?tab=links` checks will fail after T03/T04; accepted, S5 replaces S6.py with tests (D17 pattern); tickets say do not edit it
D24 2026-11-02 T03/T04 pins: Links has no expected-links lines (expected_links is not a web read); Trace takes depth, dir; Thread is read-only, one page per `before` (Older link, no accumulation); Files draws page 1 of the first PDF only (2 renders at once, 503 otherwise) and links View/Download
D25 2026-11-02 twins T09-T11 staged, not ready: M3 has API routes (T03a) and CLI reads but NO terminal text module yet (P2-I1 T05a-c screens not built), so checklist item 2 fails today. Activation steps are in each ticket: merge p2/i1, T05 text modules Textual-free, then a <=45-line reads.py seam (awp_routes + 8 mirror rows) by the supervisor. Routes known: list_cwps get_cwp list_cwas wbs_tree get_wbs_node get_path list_path_versions list_packages (project path param)
D26 2026-11-02 r6 orch dec: S5 = one tests piece (builder, full) for every merged web item. Tests live in packages/tl-web/tests (there is no tests/web: importlib mode forbids sibling imports, harness is conftest fixtures), plus the tl-api, tl-tui and tests/tools files spec 11 names. Gate = just gate over those paths, not the whole suite. S5 ports every dev/accept check (S4.py, S6.py as today's behaviour, D17 D23), CSRF walk over app.routes, WALK table (hidden = missing, five readers, every page/tab/file route; an unlisted route fails), mirror count 24, plain vs technical, viewer limits, spec 12 clauses in process. Last S5 commit git rm's dev/accept/P2-WEB1
D27 2026-11-02 T08 demo is a separate Haiku ticket (T08-demo-script.md), independent of S5, copies P1-UX2.sh seed and P1-I0.sh serve; uses the real viewer route /web/p/{project}/files/{id}/view (spec 12 omits the /web/p prefix); users demo (admin) amy dora; sqlite and postgres. Orchestrator runs it at C4
D28 2026-11-02 T03/T04 questions answered: NotImplementedError lines ("... services are not installed yet") accepted as built; commit prefix P2-WEB1-<id> is right; rule 10 (<= 5 decisive lines per command) applies
D29 2026-11-02 T09-T11 staged tickets cite dev/accept/P2-WEB1/T02.py and an acceptance script; S5 deletes them. At activation rewrite each twin: tests in the ticket as pytest on the S5 harness plus one WALK entry and the mirror count bump, no acceptance script
D30 2026-11-03 r7 seam (6cfcfb9): 7 awp mirrors in reads.py (list_cwps get_cwp list_cwas wbs_tree get_wbs_node get_path list_packages; MIRRORS 24 to 31), present re-exports awp_text cwa_text wbs_text package_text, 5 empty page stubs named in PAGE_MODULES (cwps cwas wbs packages path) so no twin edits a shared list, walk._panels takes its slugs from WALK, one marker per twin in WALK. Mirror test: the 3 single-record reads are checked as the same 404 (ABSENT; the world holds no awp record). Own diff over the 50 cap: 39 code, 30 stubs, ~40 held-test/marker lines, 55-line provided recipe
D31 2026-11-03 CWP web page: only ?q= filter; terminal d s c keys (discipline, state, group by CWA) not in i1; summary "N CWPs" pinned in the ticket (terminal builds it inside its screen)
D32 2026-11-03 CWA web page shows all areas, retired too (summary "N CWAs, M retired"): the panel partial is asked without query strings, a hidden-by-default row would 404 there
D33 2026-11-03 WBS panel has no fallback to the listing row when get_wbs_node fails (terminal has one): hidden = missing, one 404 page. ?depth= and ?unallocated=1 are the web keys
D34 2026-11-03 splits by 01-tiers 6 items 1 and 4: T09 to T09 (CWP) + T09b (CWA); T10 to T10 (WBS) + T16 (path, text module absent). Common recipe docs/tickets/P2-WEB1/TWINS.md; pytest on the S5 harness over the tl-tui awp fake (loaded by path), no acceptance script (D29)
D35 2026-11-03 screenshots: each twin test calls shoot() from provided/shot_recipe.py (uvicorn thread + Node playwright, 1440x900) into /home/user/wt/p2-web1/.accept/shots/<id>-<slug>.png (absolute, survives worktree removal); .accept/ in .gitignore; a test, not a skip, so a box without chromium fails loudly
## SEC
F1 MD fixed@b817341 login CSRF: verify_origin on POST /web/sign-in, refusal not counted by the rate limiter
F2 LO fixed@b817341 run_command(guard=True) default; JSON endpoint passes guard=False
F3 LO fixed@b817341 rate-limit tests for web sign-in (429, Retry-After, shared count with /auth/sign-in)
Security review done and re-checked P; APPROVALS line fb9c78e. Twins add no write route (no ACTION_UI row).
## OPEN
Q3 awp walking test: AGENTS.md wants a five-reader walk for a route that carries record text, but the S5 world holds no awp record. Twin tests use the tl-tui fake plus the unpatched empty world (WALK rows are route-level, vacuous on content). A real walk needs an awp seeder with a hidden CWP/area in the world: one Haiku ticket after the twins, or accept that the JSON routes' walk (P2-I1) is the proof; needs orch raised r7
Q4 Postgres: S5 reported seed_hidden_world fails on Postgres (AttachFile needs the user access word for documents), so just gate-pg packages/tl-web errors at baseline (tl-api confidentiality walk[postgres] too); needs orch raised S5
## NEXT
1. Orch: dispatch T09 T09b T10 T11 (ticket-batch-v2, review full each; 2 heavy test runs at once). They touch disjoint files; walk.py edits sit under separate markers. Merge P items, spawn r8.
2. r8: decide any 2s/gr/blk. T16: when P2-I1 T05c (path_text) is in p2/web1, add list_path_versions mirror (MIRRORS 32), present re-export, mirror case, fill T16, dispatch. T07 docs (lite) once the twins are merged: README tl-web, runbook web-client, AGENTS row, twins list.
3. M4 twins T12-T14 after M4 screens (p2/i3); write them from TWINS.md.
4. C3: twins + T07 merged. C4: full gate, gate-pg packages/tl-web (Q4 first), demo P2-WEB1, DONE round (report, learnings; S5/T08/SECFIX learnings are in their reports).
## REFS
Spec docs/build-spec/specs/web-client-i1.md (sections 3-8 are the interfaces); wave plan 2; piece specs S1-S4, S6 and tickets T01, T02, T05, T06, T15 in this directory. Acceptance scripts dev/accept/P2-WEB1/. Reports docs/reports/P2-WEB1/ (S4 has the page recipe and S5 seams; T01 has the forge_item and patch-a-read tricks). T03/T04 recipe = docstring of pages/record.py and docs/reports/P2-WEB1/S6.md. Style model: docs/tickets/P2-WEB1/S3-server-page1.md (dev/accept scripts go with S5, D26). Tests piece S5-tests.md, demo ticket T08-demo-script.md. Twin recipe TWINS.md; screenshot helper provided/shot_recipe.py; awp text modules tl_tui/{awp,cwa,wbs,package}_text.py; awp routes tl_api/routes/awp.py; fake data packages/tl-tui/tests/fakes_awp.py. Trunk claude/wizardly-allen-m2v96s @1b93a13, p2/i1 merged at c7b5276.
## TRAPS
Worktree /home/user/wt/p2-web1 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background. `DisplayMode()` takes no args (set .technical after). Hidden = missing (ADR-0016). New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144. Commit subjects P2-WEB1-<id>:. Page tickets load S4.World through importlib with S4.PAGE_SOURCE emptied (D17). A TYPE_CHECKING-only row type needs the quoted base WebLog["Row"]. forge_item has no scope argument. Ruff E501 applies in dev/accept. S3.World.upload hardcodes application/pdf. Weekly capacity ~90% (owner stop 95%): one batch per round. The panel partial is asked without the page's query strings (log.row_for loads the unfiltered list): a page may narrow rows by query, never hide rows by default. Only present.py imports tl_tui (test_web_imports, TYPE_CHECKING included): write a tl_tui type as present.<module>.<Name>. test_page_modules asserts every PAGE_MODULES name exists: a stub first. Twin tests in parallel: tl-web gate is ~4 min; heavy runs max 2.
