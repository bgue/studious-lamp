# P2-SEED STATE  r=2 base=7e52e4f C=C2 ck=0 gate=n/a wt=/home/user/wt/p2-seed
## BOARD
S1 p mrg f - generator framework, core/eng/docs/corr sections
T01 t mrg f - awp section
T05 t mrg l - fixed anchors
T02 t mrg f 7e52e4f materials; covered 52, short 98
T03 t todo f - tour wave1 seeds from project; ticket written
T04 t todo l - runbook; needs T03 merged
T06 t stg f - constraint seeds; needs trunk with core.Constraint
## DEC
D1 2026-11-07 T03 review full (drives screens); README row updated from lite
D2 2026-11-07 T04 after T03 (runbook names just tour wave1); not parallel
D3 2026-11-07 T06 staged, not dispatched: core.Constraint only on p2/i2 (ADR-0024)
## SEC
none
## OPEN
Q1 T06 context list and interfaces need completing once the trunk has core.Constraint; needs supervisor next round raised T06
## NEXT
1. Dispatch T03 (branch p2/seed-t03-tour) on its own; one workflow
2. After T03 mrg: dispatch T04 (lite)
3. When wave 2 and core.Constraint are on the trunk and merged into p2/seed: complete T06 and dispatch
4. After T04: quality section when quality.PunchItem exists; final round writes docs/reports/P2-SEED.md
## REFS
Tickets docs/tickets/P2-SEED/T0*.md; reports docs/reports/P2-SEED/*.md; project overlay dev/seed/demo_project/overlay.py; recipe `just demo-project`
## TRAPS
ProcessingJob keys excluded from same-seed key hashes; World vs DocumentsWorld differ; cost codes only via ImportCostSnapshot;
tour clock vs project calendar (today 2026-11-06) may disagree; never pkill -f; keep /tmp/pytest-of-root
