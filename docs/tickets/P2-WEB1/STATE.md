# P2-WEB1 STATE  r=3 base=685cefa C=2 ck=0 gate=n/a wt=/home/user/wt/p2-web1
## BOARD
S1 p mrg f 3145932 foundation; F1 csrf catch-all fixed; deviations ratified
S2 p mrg f 3145932 run_command + action_ui (merge 773f38c)
T06 t mrg l 3145932 licence check; blk was subject prefix only
S3 p mrg f 26708be page1 route + web mirrors; argv pin ratified (merge 0274a26)
S4 p mrg f 8fb6905 reads, WebLog, /do; ~1,160 line overrun accepted
T15 t stg f - RFI log page (T15-rfi-log-page.md)
T01 t stg f - correspondence register page, register mode only
T02 t todo f - document log; needs panel image seam first (r4)
T03 t esc f - fails 6: Textual-only logic; re-spec r4 (D16)
T04 t esc f - with T03 (D16)
T05 t stg f - PDF viewer page, js, css; file_info read added (D15)
S5 p todo f - tests piece at C3 (all spec 11 "Tests added")
T07 t todo l - docs: tl-web README, runbook web-client, AGENTS row
T08 t todo l - demo dev/demos/P2-WEB1.sh
T09-T14 t todo f - 6 twin tickets for M3 and M4 logs; wait for M3 and M4 C2
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
## SEC
Review at C4 scoped to S1-S4 (spec 11 Sec rows; offered-now check now in S4); range 1b93a13..head. Not run.
## OPEN
Q2 security review at C4 needs the owner's yes (wave plan 2) needs owner raised wave plan; orch asked, not blocking
Q3 S6 (record screen piece) adds a sixth piece over the target of 5 needs orch raised D16, decide at r4
## NEXT
1. Orch: dispatch T15, T01, T05 (all review full, disjoint paths), merge P items, then spawn r4.
2. r4: add the T02 seam (WebLog panel_image hook in log.py + 2 lines in panel_body.html, ~10 lines), write T02; read record_view.py, psets_tab.py and decide D16 (S6 piece or split T03/T04).
3. r4/r5: S5 tests piece at C3 can start once T15, T01, T02, T05 merge (needs every page for walk entries); S6 if chosen runs before it.
4. C3: S5 tests piece (spec 11 Tests added + htmlkit + test_check_licences_vendored), then T07, T08. Twins T09-T14 only after M3 and M4 C2.
5. C4: full gate and demo by orchestrator; security review (Q2); DONE round writes report.
## REFS
Spec docs/build-spec/specs/web-client-i1.md (sections 3-8 are the interfaces); wave plan 2; piece specs S1, S2, ticket T06 in this directory. Acceptance scripts dev/accept/P2-WEB1/. Specs S3-server-page1.md, S4-log-standard-reads-actions.md; tickets T15-rfi-log-page.md, T01-correspondence-log-page.md, T05-pdf-viewer.md. Reports docs/reports/P2-WEB1/S3.md, S4.md (S4 has the page recipe and S5 seams). Trunk claude/wizardly-allen-m2v96s @1b93a13; branch p2/web1 head 685cefa (r3 tickets). Style models: dev/accept/P2-W0/RM-S2.py, docs/tickets/P2-W0/S3-roles-wiring.md. Sessions ADR docs/adr/0009-authentication.md.
## TRAPS
Worktree /home/user/wt/p2-web1 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background. `DisplayMode()` takes no args. Hidden = missing (ADR-0016): module record from Record.Created alone is hidden except to system_view(). Vendoring needs the proxy-configured curl (npm registry); if refused S1 is Blocked. New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (both in every acceptance). Commit subjects P2-WEB1-<id>: (S1, S2, T06 first tries missed it). The web page tickets reuse S4.World through importlib (D17); S3.World is the file/PDF fixture (T05, T02). Weekly capacity 90%: one batch per round.
