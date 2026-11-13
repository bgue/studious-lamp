# P2-I6 STATE  r=2 base=8e7134b C=0 ck=- gate=n/a wt=/home/user/wt/p2-i6
## BOARD   (wave-1 prep only; exit items later)
S1 p mrg f f567b59 marts sync; gate 3472 P; APPROVALS
T02 t mrg f b92cfef 3 marts; lake 283 P; +hidden-IWP test
T03 t mrg l ecb78e1 audit 16 rows, D01-D05 drafts; req/WO not in seed
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
Q1 answered: P2-I5 on trunk 8e7134b 2026-11-13, merged into p2/i6
Q2 scaffold register and scaffold quantities on hire reports wait for I4-B scaffold; T03 marks them gaps with that dependency | needs orch | raised r1
## NEXT
1. Orch r2: S1 merged with trunk (I5). T02 interface change in S1 report: readiness model needs cur_core_record (refs and provided tests unchanged).
2. Done r2: T02 and T03 merged. Wave-1 prep complete (C1 of prep).
3. SR-X1 at wave-1 end (S1, T02 rows); check I5 awp events against PAYLOAD_REFS there.
4. Exit wave (B1, T01, T04, T05) only after the web increment.
## REFS
Spec and tickets: docs/tickets/P2-I6/{S1,T02,T03}-*.md. Provided tests arrive from S1 under docs/tickets/P2-I6/provided/ (T02_test_*.py). Draft tickets from T03 go to docs/tickets/P2-I6/drafts/.
## TRAPS
none yet (first check in a fresh worktree takes over 2 min, L-P1-I4-9)
