# P2-WEB1 STATE  r=2 base=8ab14cb C=0 ck=0 gate=n/a wt=/home/user/wt/p2-web1
## BOARD
S1 p mrg f 3145932 foundation; F1 csrf catch-all fixed; deviations ratified
S2 p mrg f 3145932 run_command + action_ui (merge 773f38c)
T06 t mrg l 3145932 licence check; blk was subject prefix only
S3 p disp f - server page 1 + web file mirrors (needs S1)
S4 p disp f - reads, present, WebLog, webroute, /do route
T15 t todo f - RFI log page from S4 recipe (D9; needs S4)
T01 t todo f - correspondence log (needs S4)
T02 t todo f - document log (needs S3 S4)
T03 t todo f - record screen Details, Properties (needs S4)
T04 t todo f - record tabs Links, History, Files, Thread (needs T03 S3)
T05 t todo f - PDF viewer + pdfview.js (needs S3)
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
## SEC
Review at C4 scoped to S1-S4 (spec 11 Sec rows; offered-now check now in S4); range 1b93a13..head. Not run.
## OPEN
Q2 security review at C4 needs the owner's yes (wave plan 2) needs owner raised wave plan; orch asked, not blocking
## NEXT
1. r3: verify S3 and S4 (orch merges P items; S3 regenerates openapi/uv.lock, never hand-merge). Decide any 2s/gr/blk: re-spec or split.
2. r3 batch after S4 merged: T15 (RFI page, recipe in docs/reports/P2-WEB1/S4.md), T01, T03 (disjoint pages/templates); T02 and T05 need S3 too.
3. then T04 (after T03), T02, T05; each checked against 01-tiers 6; review full (handlers, routes).
4. C3: S5 tests piece (spec 11 Tests added + htmlkit + test_check_licences_vendored), then T07, T08. Twins T09-T14 only after M3 and M4 C2.
5. C4: full gate and demo by orchestrator; security review (Q2); DONE round writes report.
## REFS
Spec docs/build-spec/specs/web-client-i1.md (sections 3-8 are the interfaces); wave plan 2; piece specs S1, S2, ticket T06 in this directory. Acceptance scripts dev/accept/P2-WEB1/. Specs S3-server-page1.md, S4-log-standard-reads-actions.md. Trunk claude/wizardly-allen-m2v96s @1b93a13; branch p2/web1 head 8ab14cb. Style models: dev/accept/P2-W0/RM-S2.py, docs/tickets/P2-W0/S3-roles-wiring.md. Sessions ADR docs/adr/0009-authentication.md.
## TRAPS
Worktree /home/user/wt/p2-web1 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background. `DisplayMode()` takes no args. Hidden = missing (ADR-0016): module record from Record.Created alone is hidden except to system_view(). Vendoring needs the proxy-configured curl (npm registry); if refused S1 is Blocked. New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (both in every acceptance). Commit subjects P2-WEB1-<id>: (S1, S2, T06 first tries missed it).
