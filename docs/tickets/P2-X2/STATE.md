# P2-X2 STATE  r=5 base=27380224 C=4 ck=1 gate=pass wt=/home/user/wt/p2-x2
## BOARD
S1 p mrg f 8b71e3b9 review P; F1 F2 LO accepted
S3 p mrg f a03515d2 stop switch; review P 3 LO; 52 P 2a; APPROVALS
S2 p mrg f 2224887f review P; APPROVALS
T01 t mrg f a9dc1eca admin stop routes+client; orch fixed wording
T02 t mrg f 11c163b9 tl agent stop|resume|stopped; 42 P
T03 t mrg f 12b0a7bb accounts screen stopped flag + held; 91 P
S3b p mrg f 2bfd7f61 review P; held accept fix; APPROVALS
S3c p mrg f 59c63a8d SR-X2 F1 fix; orch read diff
T04 t mrg f 3404c59d review P; amend 1 (T01 helper grant)
T05 t mrg f 7139c557 review P after amend 2; demo OK both adapters
T06 t mrg l acbad682 review P attempt 2
T07 t mrg f fd874cf0 DONE-gate fallout; contract excludes Agent.* (admin-only)
T08 t mrg f 21bc6a36 S1 grant fallout (tests, accept scripts)
T09 t mrg f 16a9b277 sim suite + 14 demos grant agents
T10 t mrg f 82757dab tui count pins + parity webhook exclusion; plain-walk f7 = load flake
T11 t mrg f 12478945 schema+api fallout; agent_stopped 403 error row (orch accepted)
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
(none yet; SR-X2 pass at DONE: refusals equal missing, cap text no counts, held count filtered, stop holds accept, events append-only, agent cannot stop)
S3 review F1 LO N+1 in list_stopped: ok (bounded by limit 200)
S3 review F2 LO projector bumps cur_account.version: noted, learning proposed
## OPEN
Q2 ADR-0027 amendment (filing check moves to X2) is an owner approval; S1 did not edit the ADR needs owner raised S1
Q3 pre-emptive stop of an agent that never filed (S3 item 6); built as specified, default no needs owner raised S3
## NEXT
1. Orchestrator merges p2/x2 to trunk (C4), runs the final per-directory verification if not finished, then pushes.
2. Orchestrator raises Q2 with the owner.
3. DEFERRED rows SR-X2 F2-F5 wait for a follow-up; nothing else open.
## REFS
Seam stubs: packages/tl-core/src/tl_core/services/agent_scope.py, agent_stop.py. Specs and tickets: docs/tickets/P2-X2/{S1,S2,S3,T01,T02}-*.md. Worktrees: pieces /home/user/wt/x2/s<n>, tickets /home/user/wt/x2/t<nn>. S3 report docs/reports/P2-X2/S3.md.
## TRAPS
Both pieces share proposals.py wiring only through the committed seams; S2 later adds two lines there. Gate: at most 2 builders gating at once. just check red on trunk until S1 lands (E501 in the seam docstring was wrapped by orchestrator @54cc0563).
