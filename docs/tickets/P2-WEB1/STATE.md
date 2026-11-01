# P2-WEB1 STATE  r=4 base=08902b0 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-web1
## BOARD
S1 p mrg f 3145932 foundation; F1 csrf catch-all fixed; deviations ratified
S2 p mrg f 3145932 run_command + action_ui (merge 773f38c)
T06 t mrg l 3145932 licence check; blk was subject prefix only
S3 p mrg f 26708be page1 route + web mirrors; argv pin ratified (merge 0274a26)
S4 p mrg f 8fb6905 reads, WebLog, /do; ~1,160 line overrun accepted
T15 t mrg f 88ddfe7 RFI log page (merge a2f0a1d)
T01 t mrg f 86b4338 correspondence register; transmittal rows no actions (359a3e6)
T05 t mrg f 9e5e1b3 PDF viewer page, pdfview.js (merge 0ca0d5f)
T02 t stg f - document log page; seam panel_image in tree; spec T02-document-log-page.md
S6 p stg f - record screen piece (was T03+T04); spec S6-record-screen.md
T03 t todo f - Links + Trace tabs (tab modules); write after S6 merges
T04 t todo f - Thread + Files tabs (tab modules); write after S6 merges
S5 p todo f - tests piece at C3 (all spec 11 "Tests added" + S6 files)
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
D18 2026-11-01 r4 supervisor seams (17 diff lines + 2): WebLog.panel_image(row)->str hook (default "") shown by panel_body.html above the panel text, .tl-panel-img rule in tl.css (7c0544d); present re-exports file_text (17e12bf). Both for T02
D19 2026-11-01 Q3 closed (orch approved S6). S6 cut: builder moves record_view/psets_tab/links_tab/trace_tab logic into 4 Textual-free tl_tui modules (record_text, properties_text, links_text, trace_text; old names re-exported, no test edited), adds mirrors conformance + trace, action_views helper in log.py, pages/record.py frame with Details, Properties, History and a lazy tab registry (TAB_MODULES record_links/trace/thread/files). Links, Trace, Thread, Files tabs become Haiku tickets T03 (links+trace) and T04 (thread+files) after S6 merges, one tab module + template each
D20 2026-11-01 documents web log has no actions in i1: no document command has an ACTION_UI row (terminal builds them inside its screen); T02 overrides actions_for to []. Issue/supersede/void revision and transmittals stay terminal-only; follow-up for the Phase 2 plan, not this increment
D21 2026-11-01 S6 acceptance carries one pytest line (existing tl-tui record/psets/links/trace tests, move-only regression sniff, as D13 did for S3); new tests stay deferred to S5. Orchestrator may strike the line; then the move is checked by the script only
D22 2026-11-01 T01 open point left as built: status line counts all loaded rows, the terminal counts the filtered rows; S5 pins the web behaviour; revisit at DONE if the owner wants parity
## SEC
Review at C4 scoped to S1-S4 and S6 (spec 11 Sec rows; offered-now check in S4; hidden record = missing in S6); range 1b93a13..head. Not run.
## OPEN
Q2 security review at C4 needs the owner's yes (wave plan 2) needs owner raised wave plan; orch asked, not blocking
## NEXT
1. Orch: dispatch T02 (review full) and S6 (piece, full) in parallel (disjoint paths; both read log.py, S6 edits it: T02 does not). Merge P items, spawn r5.
2. r5: write T03 and T04 (tab modules) from the S6 report recipe; commit any held interface. Run the 01-tiers 6 checklist on each.
3. r5/r6: S5 tests piece once T02, S6 and T03/T04 are in the tree (walk entries need every page, plus the S6 files); C3 follows.
4. C3: S5, then T07 docs and T08 demo. Twins T09-T14 only after M3 and M4 C2.
5. C4: full gate and demo by orchestrator; security review (Q2); DONE round writes the report and learnings (proposed ones sit in docs/reports/P2-WEB1/*.md "Learnings").
## REFS
Spec docs/build-spec/specs/web-client-i1.md (sections 3-8 are the interfaces); wave plan 2; piece specs S1-S4, S6 and tickets T01, T02, T05, T06, T15 in this directory. Acceptance scripts dev/accept/P2-WEB1/. Reports docs/reports/P2-WEB1/ (S4 has the page recipe and S5 seams; T01 has the forge_item and patch-a-read tricks). Trunk claude/wizardly-allen-m2v96s @1b93a13; branch p2/web1 head = base above (state commit follows). Style models: dev/accept/P2-WEB1/T15.py, docs/tickets/P2-WEB1/S3-server-page1.md.
## TRAPS
Worktree /home/user/wt/p2-web1 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background. `DisplayMode()` takes no args (set .technical after). Hidden = missing (ADR-0016). New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144. Commit subjects P2-WEB1-<id>:. Page tickets load S4.World through importlib with S4.PAGE_SOURCE emptied (D17). A TYPE_CHECKING-only row type needs the quoted base WebLog["Row"]. forge_item has no scope argument. Ruff E501 applies in dev/accept. S3.World.upload hardcodes application/pdf. Weekly capacity ~90% (owner stop 95%): one batch per round.
