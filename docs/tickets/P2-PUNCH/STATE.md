# P2-PUNCH STATE  r=1 base=bb6f855b C=0 ck=0 gate=n/a wt=/home/user/wt/p2-punch
## BOARD   (r1: plan, two piece specs and nine tickets written; nothing dispatched; `todo` = spec written, deps unmet)
S1 p todo f - schema + module spec; human gate (APPROVALS); dispatch r2 alone
S2 p todo f - six commands, subject join, row; needs S1; human gate
T01 t todo f - read views + provided test (supervisor commits it after S2 merges); needs S2
T02 t todo f - `tl punch` writes and reads; needs T01
T03 t todo f - 3 API routes + PUNCH_COMMANDS door; needs T01
T05 t todo f - punch_tools.py: 2 reads + propose_punch_item; needs T01
T04 t todo f - client reads + quality_command + fake; needs T03
T06 t todo f - punch_text, log, record screen c/v/o, palette; needs T04
T07 t todo f - generator quality section + roster grant + pins; needs S2
T08 t todo f - dev/demos/P2-PUNCH.sh seven clauses; needs T02 T03 T04 T05 T06 T07
T09 t todo l - docs, runbook, reference; needs T08
## DEC
D1 2026-11-11 module `quality`, one record `quality.PunchItem`, table cur_quality_punch_item; README "Record shape"
D2 2026-11-11 states Open, Cleared, Verified, Void; reopen from Cleared or Verified; Void only terminal; assignment is a field; S1
D3 2026-11-11 seven words: quality.view read; punch.raise|edit|clear user; punch.verify|reopen|void controller; no new setting; S1
D4 2026-11-11 verifier differs from clearer (fixed message); raiser is the context actor, never an input; S2
D5 2026-11-11 hidden when the source record is hidden: SUBJECT_LINKS row ported from p2/i4a shape, punch row only; S2 (core gate)
D6 2026-11-11 numbering {project}-PUN-{seq:4}, gap-free; S1
D7 2026-11-11 PROPOSABLE only propose_punch_item; Edit, Clear (direct) and Verify, Reopen, Void (acts) excluded; S2
D8 2026-11-11 offline class draft_only; all events feed_policy none (no core feed change); S1
D9 2026-11-11 writes: API door by T03 (_module_specs), TUI door quality_command by T04; no web files
D10 2026-11-11 routes use guard("document.read") then require_word quality.view (the constraints _view_reader pattern); T03
D11 2026-11-11 tests ride in tickets and pieces; only T01 gets a provided test, committed at r3 once S2 names exist
D12 2026-11-11 Phase 3 compatibility is additive (kind, response_cycle, escalation_level); table in README
D13 2026-11-11 S1 adds tl-mod-quality to the four consumer pyprojects and uv.lock once: no ticket touches uv.lock
## SEC
(none yet; rows in README "Security rows")
## ORCH 2026-11-11 answers
D14 Q5: S1 may add the new event names to the feed-policy list in tl_core/feed/cards.py if a test refuses them (one line); compat baseline update allowed (additive).
D15 Q1: no fixed order with p2/i4a; whichever merges to trunk second unions SUBJECT_LINKS rows and proposable_exclusions.toml.
D16 Q3: T06 uses the generic record-screen action path if it covers clear/verify/reopen; else quality_command plus a form.
D17 Q4: two hops claimed; the three-hop case is a known limit (DEFERRED line at close, with outside review 1 F5).
D19 S1 blk: FROZEN valid-time baseline never grows; new punch events get optional valid-time `at` (Raised, Edited, Reopened, Voided)
D18 Q2: default applied (superuser verifies, never the clearer; verified can reopen); owner told.
## OPEN
Q1 merge order with p2/i4a: both add SUBJECT_LINKS rows and tests/tools/proposable_exclusions.toml; default punch merges first (roadmap 4a before 4b), I4A then unions the rows | needs orch | raised r1
Q2 who verifies: default module superuser, never the clearer; reopen and void controller acts; a verified item can be reopened | needs owner | raised r1 (default applied)
Q3 TUI write keys c, v, o use quality_command and a form; if the generic record-screen action path is preferred instead, say so before r7 | needs orch | raised r1
Q4 chain longer than two hops (constraint on a punch item raised from a requisition of a hidden IWP) is not claimed (_HOPS 2) | needs orch | raised r1
Q5 POLICY_EVENT_TYPES in tl_core/feed/cards.py may reject new quiet events; S1 stops, does not edit core | needs orch | raised r1
## NEXT
1. Orchestrator: dispatch S1 alone (human gate: APPROVALS line at merge; consumer pyproject and uv.lock lines are in it).
2. After S1 merges: S2 alone (core gate). Then r4: supervisor commits provided/T01_test_views.py from the S2 report, then T01 with T07.
3. r5 [T02, T03, T05] (disjoint: tl-cli, tl-api, tl-mcp); r6 T04; r7 T06; r8 T08; r9 T09. After each merge `just gen` last, pinned lists as union.
4. Between rounds a supervisor reads the merged reports and re-specs a ticket whose named interface moved (names marked in each ticket: PunchRow, PunchDetail, PunchPage, PUNCH_COMMANDS, punch_world.py).
5. Close: `just check`, whole gate, `just gate-pg` on touched dirs (tests/confidentiality, quality tests), `just demo P2-PUNCH`, security rows with the next wave review.
6. DEFERRED lines for the orchestrator: web punch log and record page; walkdown fast-entry screen and `d` key; photo slot; thread target /raise punch; feed cards; Phase 3 Issue engine takeover and inspections; Phase 4 System/Subsystem links and punch-A completion checks; per-project move of a quality word.
## REFS
Plan `docs/tickets/P2-PUNCH/README.md`; pieces `S1-schema-and-module.md`, `S2-commands-and-engine.md`; tickets `T01..T09`. Shape sources (read-only, branch p2/i4a): `docs/tickets/P2-I4A/`, `packages/tl-core/src/tl_core/confidentiality.py` (SUBJECT_LINKS), `tests/tools/proposable_exclusions.toml`, `packages/tl-modules/requisitions/tests/req_world.py`. Patterns on the trunk: `tl_mcp/iwp_tools.py`, `tl_api/routes/constraints.py` (_view_reader), `tl_cli/awp_iwp_write.py`, `dev/demos/P2-I3.sh`. No provided test or stub is in the tree yet.
## TRAPS
Gates name test files or one package (OOM on 16 GB); tests/tools gate about 10 min (background); gate-pg on tests/confidentiality about 26 min; demo-project gates take minutes; never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; tests dialect-neutral; `uv sync --all-packages` in a fresh worktree before pyright; an IWP is not confidential, so hidden-source tests use a restricted correspondence item made by commands.
