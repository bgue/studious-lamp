# P2-INT STATE  r=1 base=2f1d886 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-int
## BOARD
S1 p stg f - event intent: model, column, hash ext, archive, restore, bronze
S2 p stg f - boundary: validation, carrier, API reads, proposals, walk (after S1)
T01 t stg f - tl:valid_time annotation + rule + lint (schema label)
T02 t stg f - CLI --why/--next/--toward (after S2)
T03 t stg f - MCP intent parameter (after S2)
T04 t stg f - TUI History/Activity intent text (after S2)
T05 t stg l - demo driver (after T02-T04)
## DEC
D1 2026-11-07 plan from ADR-0025 answers F3-F6,F13,F14 + ADR-0026 F5 + ADR-0027 F9; no PLANCHK (7 items, ADRs already checked)
D2 2026-11-07 S1 refuses non-null intent through ONE function check_intent (S2 replaces its body); S1 may add one line in tl_api run_command
D3 2026-11-07 proposal accept re-reads intent from the Created event (read_stream v1); no projection or schema change
D4 2026-11-07 T01 lint uses a shrink-only baseline file (tests/tools/valid_time_baseline.toml) so wave 3 classes must tag or give a reason
D5 2026-11-07 entries that bypass the dispatcher (sim, rules, integration, jobs) keep NULL intent; S2 reports them, does not extend
## SEC
Rows (no findings yet): intent references (S2: hidden = unknown, ids stored, same code/text); hash extension (S1: optional last part, old vectors unchanged, byte-identical re-seal).
## OPEN
Q1 approver lines for S1, S2, T01 are APPROVALS entries made by the orchestrator at merge needs orch raised r1
## NEXT
1. r1 done: dispatch S1 + T01 (disjoint paths; one builder + one ticket workflow).
2. After S1 merges (C1): r2 supervisor verifies board, releases S2.
3. After S2 merges (C2): r3 commits provided tests for T02/T03/T04, checks the DTO and write-path points they name, releases the three.
4. T05 after T02-T04 (C3); C4 demo green both adapters; orchestrator: full gate, gate-pg on touched dirs, short Sec review on S1+S2.
5. Wave 3 must not start before C2.
## REFS
Specs: README.md (objective, demo, order); ADRs 0025 (answers F3-F6,F13,F14), 0026 F5, 0027 F9. Tickets T02-T05 are drafts: re-read their Interfaces against S2's merged code before release.
## TRAPS
none yet. Postgres events DDL is `postgres/ddl.py` EVENTS_DDL; SQLite has no ADD COLUMN IF NOT EXISTS (probe PRAGMA table_info).
