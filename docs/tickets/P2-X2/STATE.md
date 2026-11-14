# P2-X2 STATE  r=2 base=27380224 C=0 ck=- gate=n/a wt=/home/user/wt/p2-x2
## BOARD
S1 p disp f - re-dispatched amendment 1 (explicit grants only); branch p2/x2-s1-filing-check
S3 p mrg f a03515d2 stop switch; review P 3 LO; 52 P 2a; APPROVALS
S2 p todo f - queue cap spec written r2; dispatch after S1 merged; setting gated (95)
T01 t todo f - spec r2: routes + ApiClient stop/resume/stopped; ready (S3 merged)
T02 t todo f - spec r2: tl agent stop/resume/stopped; ready (S3 merged)
T03 t todo f - accounts screen flag + held count; waits T01
T04 t todo f - walks, AGENT_MAY_NOT rows; waits S1,S2,S3,T03
T05 t todo f - demo driver dev/demos/P2-X2.sh; waits T02,T04
T06 t todo l - runbook accounts-and-access.md grant checklist; waits T05
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
## SEC
(none yet; SR-X2 at wave end: refusals equal missing, cap text no counts, held count filtered, stop holds accept, events append-only, agent cannot stop)
S3 review F1 LO N+1 in list_stopped: ok (bounded by limit 200)
S3 review F2 LO projector bumps cur_account.version: noted, learning proposed
## OPEN
Q2 ADR-0027 amendment (filing check moves to X2) is an owner approval; S1 does not edit the ADR needs orch raised S1
Q3 S3 Q1: an admin cannot stop an agent before its first filing (built as spec'd); pre-emptive stop wanted? needs owner raised S3 (default: no)
## NEXT
1. Orchestrator dispatches T01 and T02 now (one workflow, disjoint paths; both depend only on S3) beside S1.
2. After S1 merged (C1): dispatch S2 (S2-queue-cap.md), then merge the 95 setting line to APPROVALS before S2 merge.
3. After T01 merged: round 3 writes T03; after T02+T04 write T05, then T06.
4. T04 needs S1, S2, S3, T03 merged; walks five readers of held count and stopped list, cap text, AGENT_MAY_NOT already added by T01.
5. DONE round: report, learnings (account-stream projectors move cur_account.version), AGENTS.md rows, runbook grant checklist.
## REFS
Seam stubs: packages/tl-core/src/tl_core/services/agent_scope.py, agent_stop.py. Specs and tickets: docs/tickets/P2-X2/{S1,S2,S3,T01,T02}-*.md. Worktrees: pieces /home/user/wt/x2/s<n>, tickets /home/user/wt/x2/t<nn>. S3 report docs/reports/P2-X2/S3.md.
## TRAPS
Both pieces share proposals.py wiring only through the committed seams; S2 later adds two lines there. Gate: at most 2 builders gating at once. just check red on trunk until S1 lands (E501 in the seam docstring was wrapped by orchestrator @54cc0563).
