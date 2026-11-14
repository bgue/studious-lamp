# P2-X2 STATE  r=1 base=a2e3ddc4 C=0 ck=- gate=n/a wt=/home/user/wt/p2-x2
## BOARD
S1 p disp f - filing check; spec committed; seam stub+wiring in proposals.py
S3 p disp f - stop switch; spec committed; schema gated (95)
S2 p todo f - queue cap; waits S1 merged; setting gated (95)
T01 t todo f - API routes, ApiClient stop/resume/list; waits S3
T02 t todo f - tl agent stop/resume/stopped; waits S3
T03 t todo f - accounts screen flag + held count; waits T01
T04 t todo f - walks, AGENT_MAY_NOT rows; waits S1,S2,S3,T03
T05 t todo f - demo driver dev/demos/P2-X2.sh; waits T02,T04
T06 t todo l - runbook accounts-and-access.md grant checklist; waits T05
## DEC
D1 2026-11-14 order in submit/propose: replay, check_filing, require_not_stopped, budget, precheck; wired by supervisor r1 (specs S1 item 3)
D2 2026-11-14 filing check applies to module commands (command_index); core commands unchanged (Q1)
D3 2026-11-14 seams = two stub modules so S1 (agent_scope.py) and S3 (agent_stop.py) have disjoint paths
D4 2026-11-14 accept check skipped for ACTION_PROPOSAL_TOOL (person-filed action proposals have no agent stop)
D5 2026-11-14 ADR-0029 d6: is_stopped(conn, agent) is the one callable stop check (S3 item 5)
## SEC
(none yet; SR-X2 at wave end: refusals equal missing, cap text no counts, held count filtered, stop holds accept, events append-only, agent cannot stop)
## OPEN
Q1 Core commands (CreateRecord, AddLink...) have no module word; filing check skips them. OK, or require a project-level agent grant? needs orch raised S1
Q2 ADR-0027 amendment (filing check moves to X2) is an owner approval; S1 does not edit the ADR needs orch raised S1
## NEXT
1. Orchestrator runs S1, S3 builders (max 2 gating at once); merge S1 = C1, then S3 and S2 = C2.
2. Round 2: verify merges; write S2 spec (cap setting key, counted after filing check, before budget, fixed text, no counts; project = command.scope's project).
3. After S3 merged: write T01, T02 (disjoint paths), then T03.
4. Then T04, T05, T06; DONE round: report, learnings, AGENTS.md rows.
## REFS
Seam stubs: packages/tl-core/src/tl_core/services/agent_scope.py, agent_stop.py. Specs: docs/tickets/P2-X2/S1-*.md, S3-*.md. Piece worktrees /home/user/wt/x2/s<n>.
## TRAPS
Both pieces share proposals.py wiring only through the committed seams; neither may edit it. gate: at most 2 builders gating at once.
