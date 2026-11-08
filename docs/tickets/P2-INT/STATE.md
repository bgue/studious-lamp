# P2-INT STATE  r=3 base=2f1d886 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-int
## BOARD
S1 p mrg f 9c60a80 event intent: model, column, hash ext, archive
S2 p mrg f 0fc06f1 boundary: validation, carrier, API reads, proposals, walk (after S1)
T01 t mrg f c55317a tl:valid_time tag + frozen baseline
T02 t mrg f 9e897a7 CLI --why/--next/--toward on record+link (D6)
T03 t mrg f e337656 MCP intent param on 12 propose submits
T04 t blk f - HELD: needs P2-INS on trunk (History tab becomes Activity); TUI History panel + embedded redact
T05 t stg l - demo driver (after T02-T04)
## DEC
D1 2026-11-07 plan from ADR-0025 answers F3-F6,F13,F14 + ADR-0026 F5 + ADR-0027 F9; no PLANCHK (7 items, ADRs already checked)
D2 2026-11-07 S1 refuses non-null intent through ONE function check_intent (S2 replaces its body); S1 may add one line in tl_api run_command
D3 2026-11-07 proposal accept re-reads intent from the Created event (read_stream v1); no projection or schema change
D4 2026-11-07 T01 lint uses a shrink-only baseline file (tests/tools/valid_time_baseline.toml) so wave 3 classes must tag or give a reason
D5 2026-11-07 entries that bypass the dispatcher (sim, rules, integration, jobs) keep NULL intent; S2 reports them, does not extend
D6 2026-11-08 CLI has no write point (440 direct handle_* sites, no dispatcher): T02 limited to record create|void and link add|retract via run_with_intent (check_intent + intent_scope); other groups later
D7 2026-11-08 T04: Activity screen is schedule activities, Trace has no intent: History tab only, panel under table; embedded history() must redact (core record_history does not)
D8 2026-11-08 T03: all MCP write tools are propose tools via proposals.submit: param + pass-through only; core Intent model is the param type
## SEC
Rows (no findings yet): intent references (S2: hidden = unknown, ids stored, same code/text); hash extension (S1: optional last part, old vectors unchanged, byte-identical re-seal).
## OPEN
Q1 approver lines for S1, S2, T01 are APPROVALS entries made by the orchestrator at merge needs orch raised r1
## NEXT
1. r3 done: T02, T03, T04 ready (disjoint paths; one workflow of 3). Gates: T02 cli test files, T03 tl-mcp tests, T04 tui test files (see relay GATE lines).
2. After the three merge (C3): r4 writes T05 demo ticket and dispatches it.
3. C4 = demo green both adapters; orchestrator: full gate, gate-pg on touched dirs, short Sec review on S1+S2.
4. Wave 3 may start now (C2 reached); new commands there need no intent code.
5. Follow-up (not P2-INT): intent flags for other CLI groups; web action route forms and MCP carry none.
## REFS
Specs: README.md (objective, demo, order); ADRs 0025 (answers F3-F6,F13,F14), 0026 F5, 0027 F9. Provided tests (committed r3): packages/tl-cli/tests/test_intent_flags.py, packages/tl-tui/tests/test_intent_text.py. T03 has none. T05 still a draft. S2 report: docs/reports/P2-INT/S2.md (tl events reads without redaction: T02 notes it).
## TRAPS
none yet. Postgres events DDL is `postgres/ddl.py` EVENTS_DDL; SQLite has no ADD COLUMN IF NOT EXISTS (probe PRAGMA table_info).
