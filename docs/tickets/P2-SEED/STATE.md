# P2-SEED STATE  r=3 base=7a0b140b C=C2 ck=0 gate=n/a wt=/home/user/wt/p2-seed
## BOARD
S1 p mrg f - generator framework, core/eng/docs/corr sections
T01 t mrg f - awp section (report exists)
T02 t mrg f - materials section
T05 t mrg l - fixed anchors
T03 t mrg f - tour seeds from project (report exists; verify in log)
T04 t mrg l - runbook (report exists; verify in log)
T06 t mrg f - constraints section (constraints.py on trunk)
T07 t mrg f 19ca2fa schedule + 4 snapshots; 11 P
T08 t disp f 7b91594 att2: add GeneralRequisitionType to demo standards
T09 t disp f - att2: lhartmann awp superuser (2nd signer)
T10 t stg f - weekly plans; needs T09; stub not yet added
T11 t stg f - progress; needs T09; stub not yet added
## DEC
D1 2026-11-14 audit: gaps = requisitions, schedule, weekly plan, progress; cost not a gap (ImportCostSnapshot in awp, materials)
D2 2026-11-14 stubs T07 T08 T09 registered by supervisor (210f780a) so ticket paths are disjoint; ORDER: awp, schedule, constraints, release, materials, quality, requisitions
D3 2026-11-14 issuing IWPs split out as T09: no seed section leaves an IWP Issued, weekly and progress need that
D4 2026-11-14 old plan kept: this round extends it (T07-T11), README has a new section; round numbering continues at r3
## SEC
none
## OPEN
Q1 T09 may need a builder piece if readiness cannot compute in process or sign-off roles have no roster holder; needs orch raised T09
Q2 T08 may need roster grants (requisitions words) in core.py; outside T08 paths; needs supervisor next round raised T08
Q3 box: one heavy slot busy; the 3 dispatched tickets gate one after another
## NEXT
1. After merges of T07 T08 T09: add stubs weekly (after release) and progress (after weekly) in ORDER and __init__; dispatch T10, T11 with full text
2. Insert section order: release, weekly, progress before materials is NOT needed; keep weekly, progress last
3. Handle 2s, gr or blk items; resolve Q1 and Q2 by re-spec or escalate
4. Final round: report docs/reports/P2-SEED/ and AGENTS.md row if the generator line needs it
## REFS
Tickets docs/tickets/P2-SEED/T07..T11; stubs dev/seed/demo_project/{schedule,requisitions,release}.py; test pattern tests/tools/test_demo_project_quality.py
## TRAPS
Child-process tests only (generator sets TL_SCHEMA_DIR); ORDER names must have a registered section (KeyError in __main__); ProcessingJob keys excluded from key hashes; cost codes only via ImportCostSnapshot; never pkill -f
