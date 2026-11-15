# P2-X2 STATE  r=4 base=27380224 C=1 ck=- gate=n/a wt=/home/user/wt/p2-x2
## BOARD
S1 p mrg f 8b71e3b9 review P; F1 F2 LO accepted
S3 p mrg f a03515d2 stop switch; review P 3 LO; 52 P 2a; APPROVALS
S2 p mrg f 2224887f review P; APPROVALS
T01 t mrg f a9dc1eca admin stop routes+client; orch fixed wording
T02 t mrg f 11c163b9 tl agent stop|resume|stopped; 42 P
T03 t mrg f 12b0a7bb accounts screen stopped flag + held; 91 P
T04 t disp f - walks A/B/C; merged names pasted r4
T05 t stg f - demo sh+py, both adapters; behind T04; names pasted
T06 t stg l - runbook, steps 15-21; behind T05; outputs pasted
## DEC
D1 2026-11-14 order in submit/propose: replay, check_filing, require_not_stopped, check_queue_cap, budget, precheck; cap line added by S2 (D6)
D2 2026-11-14 filing check: module commands need the module `user` word; core commands need an explicit module role on the scope (Q1 closed)
D3 2026-11-14 seams = two stub modules so S1 (agent_scope.py) and S3 (agent_stop.py) have disjoint paths
D4 2026-11-14 accept check skipped for ACTION_PROPOSAL_TOOL (person-filed action proposals have no agent stop)
D5 2026-11-14 ADR-0029 d6: is_stopped(conn, agent) is the one callable stop check (S3 item 5)
D6 2026-11-14 S2 cap: key ai.agents.max_pending_per_project (int, default 100, 1..100000, platform|company|project); queue = command.scope; count = pending rows the filing agent's viewer may read (filter before count); fixed text, no counts; new QueueFullError, row queue_full 429. Hidden-carrying proposals do not count against the cap (trade-off in spec)
D7 2026-11-14 S1 amendment 1: filing counts explicit grants only (source granted|granted_all_modules|admin); agent fixtures get GrantModuleRole in shared helpers (ensure_agent in packages/tl-mcp/tests/mcp_harness.py, packages/tl-api/tests/harness.py, confseed)
D8 2026-11-14 proposals test path is tests/services/test_proposals.py (never packages/tl-core/tests/test_proposals.py); S1 spec on its branch still names the old path in its Gate line: orchestrator fixes on merge or tells the builder
D9 2026-11-14 T01 adds three admin routes (guard actions admin.agents.stop|resume|list) and the AGENT_MAY_NOT rows in test_auth_review.py as a consequential pin; T04 does not repeat them, it only walks
D10 2026-11-15 T03 adds ClientInterface.list_stopped_agents (mirror of ApiClient) and an agent's Filing/Held lines in the panel; screen counts nothing; no filing in its tests (S1 grant not merged)
D11 2026-11-15 T04 staged with names only (S1/S2 helpers unmerged): supervisor pastes merged signatures at dispatch; T01 already added AGENT_MAY_NOT rows, T04 asserts them
D13 2026-11-15 r4: S1 Gate line fixed to tests/services/test_proposals.py (D8 closed); T04 traps pasted: McpHarness.call auto-grants (no-word case calls server.call_tool directly), helper grants P999 (missing scope is project:NOPE)
D12 2026-11-15 T06 puts the setting reference in runbooks/settings.md (no reference page exists); T05 python driver capped 250 lines
## SEC
(none yet; SR-X2 at wave end: refusals equal missing, cap text no counts, held count filtered, stop holds accept, events append-only, agent cannot stop)
S3 review F1 LO N+1 in list_stopped: ok (bounded by limit 200)
S3 review F2 LO projector bumps cur_account.version: noted, learning proposed
## OPEN
Q2 ADR-0027 amendment (filing check moves to X2) is an owner approval; S1 does not edit the ADR needs orch raised S1
Q3 S3 Q1: an admin cannot stop an agent before its first filing (built as spec'd); pre-emptive stop wanted? needs owner raised S3 (default: no)
## NEXT
1. Orchestrator dispatches T04 (docs/tickets/P2-X2/T04-scope-walks.md, branch p2/x2-t04-scope-walks, review full); merges on P.
2. After T04 mrg: dispatch T05 (demo); after T05 mrg: T06 (lite). Nothing runs beside T04 except builders on other increments.
3. DONE round: report, learnings (account-stream projectors move cur_account.version; generated /commands body names; AGENT_MAY_NOT for every admin.command.*; McpHarness.call auto-grants), AGENTS.md rows (agent stop, queue cap), SR-X2 at wave end.
## REFS
Seam stubs: packages/tl-core/src/tl_core/services/agent_scope.py, agent_stop.py. Specs and tickets: docs/tickets/P2-X2/{S1,S2,S3,T01,T02}-*.md. Worktrees: pieces /home/user/wt/x2/s<n>, tickets /home/user/wt/x2/t<nn>. S3 report docs/reports/P2-X2/S3.md.
## TRAPS
Both pieces share proposals.py wiring only through the committed seams; S2 later adds two lines there. Gate: at most 2 builders gating at once. just check red on trunk until S1 lands (E501 in the seam docstring was wrapped by orchestrator @54cc0563).
