# P2-I6 STATE  r=1 base=4624fcf C=0 ck=- gate=n/a wt=/home/user/wt/p2-i6
## BOARD   (wave-1 prep only; exit items later)
S1 p disp f - B2 marts sync pass; spec staged r1
T02 t stg f - gold marts SQL; waits S1 merged
T03 t stg l - blocked: needs P2-I5 merged to trunk
B1 p todo f - exit wave 5; not staged
T01 t todo f - exit wave 5; needs B1
T04 t todo f - exit demo; needs T01 T02
T05 t todo - - phase report; orchestrator
## DEC
D1 2026-11-13 r1: S1 loads cur_materials_movement (append by seq) and cur_materials_stock (whole replace) into silver; no lot or item silver (mart_materials groups by kind, not item); S1
D2 2026-11-13 r1: gold marts are SQL files tl_lake/models/<mart>.sql run by tl_lake.gold inside the sync transaction (lake pass and xer pass), skip when a needed table is missing; S1
D3 2026-11-13 r1: marts never carry check detail, resolve_via or payload JSON (may name hidden records); S1 T02
D4 2026-11-13 r1: mart_schedule_vs_readiness is per published snapshot (aggregate of the latest evaluation per IWP up to the data date), not per activity; S1
D5 2026-11-13 r1: T02 Haiku-ability checklist yes after S1 (3 SQL files, provided tests, <=6 context files); T03 yes
## SEC
(SR-X1 range 4624fcf..head at wave 1 end: S1 and T02 rows; proofs in S1 "Sec")
## OPEN
Q1 P2-I5 merge to trunk date, T03 start | needs orch | raised r1
Q2 scaffold register and scaffold quantities on hire reports wait for I4-B scaffold; T03 marks them gaps with that dependency | needs orch | raised r1
## NEXT
1. Orch: dispatch S1 (builder), gate, review full, merge; then spawn r2.
2. r2: verify S1 merged; check S1 report interface equals spec; dispatch T02 (copy provided tests).
3. r2/r3: when P2-I5 is on trunk, dispatch T03 (lite).
4. Exit wave (B1, T01, T04, T05) only after the web increment.
## REFS
Spec and tickets: docs/tickets/P2-I6/{S1,T02,T03}-*.md. Provided tests arrive from S1 under docs/tickets/P2-I6/provided/ (T02_test_*.py). Draft tickets from T03 go to docs/tickets/P2-I6/drafts/.
## TRAPS
none yet (first check in a fresh worktree takes over 2 min, L-P1-I4-9)
