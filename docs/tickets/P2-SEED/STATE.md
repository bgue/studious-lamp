# P2-SEED STATE  r=4 base=7a0b140b C=C2 ck=0 gate=n/a wt=/home/user/wt/p2-seed
## BOARD
S1 p mrg f - generator framework, core/eng/docs/corr sections
T01 t mrg f - awp section (report exists)
T02 t mrg f - materials section
T05 t mrg l - fixed anchors
T03 t mrg f - tour seeds from project (report exists; verify in log)
T04 t mrg l - runbook (report exists; verify in log)
T06 t mrg f - constraints section (constraints.py on trunk)
T07 t mrg f 19ca2fa schedule + 4 snapshots; 11 P
T08 t mrg f de8a92c req 4 kinds + WO lifecycle; 16 P
T09 t mrg f cc3957b release: 2 sign-offs, issue, start; 17 P
T10 t mrg f 2d56cda 5 weekly plans; MissReason; 12 P
T11 t disp f 7e9e776 att3: scope section before constraints (AddIwpScope refused on Ready)
## DEC
D1 2026-11-14 audit: gaps = requisitions, schedule, weekly plan, progress; cost not a gap (ImportCostSnapshot in awp, materials)
D2 2026-11-14 stubs T07 T08 T09 registered by supervisor (210f780a) so ticket paths are disjoint; ORDER: awp, schedule, constraints, release, materials, quality, requisitions
D3 2026-11-14 issuing IWPs split out as T09: no seed section leaves an IWP Issued, weekly and progress need that
D4 2026-11-14 old plan kept: this round extends it (T07-T11), README has a new section; round numbering continues at r3
D5 2026-11-14 seed had no scope items (AddIwpScope frozen after issue) so T11 adds section scope before release; ORDER now ..constraints,scope,release,materials,quality,requisitions,weekly,progress
D6 2026-11-14 demo awp standards lacked MissReason; T10 owns standards.yaml edit; T11 may not touch it
D7 2026-11-14 T10 T11 disjoint (T11 test runs without weekly): dispatched together
## SEC
none
## OPEN
Q3 box: gates are slow (~6 min each); T10 and T11 gate one after another
## NEXT
1. Merge T10 T11 on pass; run combined tests/tools/test_demo_project*.py once after both merge (full ORDER run)
2. Handle 2s, gr or blk; T11 may block on commodity without a manual step (standards edit = decision)
3. Check the sign-off dates note: readiness evaluated at TODAY, signatures earlier (cosmetic, T09 learning)
4. Final round: report docs/reports/P2-SEED/ and AGENTS.md row if needed
## REFS
Tickets docs/tickets/P2-SEED/T07..T11; stubs dev/seed/demo_project/{scope,weekly,progress}.py; test pattern tests/tools/test_demo_project_quality.py
## TRAPS
Child-process tests only (generator sets TL_SCHEMA_DIR); ORDER names must have a registered section (KeyError in __main__); ProcessingJob keys excluded from key hashes; cost codes only via ImportCostSnapshot; never pkill -f
