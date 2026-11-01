# P2-WEB1 STATE  r=1 base=1b93a13 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-web1
## BOARD
S1 p stg f - foundation: tl-web pkg, cookie session, CSRF, headers, vendored js
S2 p stg f - run_command + tl_tui/action_ui.py (Textual-free)
T06 t stg l - licence check reads VENDORED.toml
S3 p todo f - server page 1 + web file mirror routes (needs S1)
S4 p todo f - reads, present, log, web actions + POST /do, RFI log (needs S1 S2)
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
## SEC
Review at C4 scoped to S1-S4 (spec 11 Sec rows; offered-now check now in S4); range 1b93a13..head. Not run.
## OPEN
Q1 S4 size: cut the RFI page (pages/rfis.py, templates) to a Haiku ticket once reads/log/present are in the tree? needs supervisor r2 raised D8
Q2 security review at C4 needs the owner's yes (wave plan 2) needs owner raised wave plan
## NEXT
1. r2: verify S1, S2, T06 against git log. S1 and S2 merge first (registries); S3 and S4 regenerate openapi/uv.lock, never hand-merge.
2. r2 batch: S3 (spec 8, needs S1; also tl_web/files.py cookie mirrors) and S4 (spec 6, 7 plus actions per D3; htmlkit.py is S5's). Commit stubs/interfaces S4 needs.
3. After S4 (C2): T01, T02, T03, T05 (disjoint paths); T04 after T03; check each against 01-tiers 6.
4. C3: S5 tests piece, then T07 docs, T08 demo. Twins T09-T14 only after M3 and M4 C2.
5. C4: full gate and demo by orchestrator; security review (Q2); DONE round writes report.
## REFS
Spec docs/build-spec/specs/web-client-i1.md (sections 3-8 are the interfaces); wave plan 2; piece specs S1, S2, ticket T06 in this directory. Acceptance scripts dev/accept/P2-WEB1/. Style models: dev/accept/P2-W0/RM-S2.py, docs/tickets/P2-W0/S3-roles-wiring.md. Sessions ADR docs/adr/0009-authentication.md.
## TRAPS
Worktree /home/user/wt/p2-web1 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background. `DisplayMode()` takes no args. Hidden = missing (ADR-0016): module record from Record.Created alone is hidden except to system_view(). Vendoring needs the proxy-configured curl (npm registry); if refused S1 is Blocked.
