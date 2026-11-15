# P2-FORMS STATE  r=1 base=b91ee33d C=C0 ck=0 gate=n/a wt=/home/user/wt/forms-plan
Plan `docs/tickets/P2-FORMS/README.md` (plan-checked via forms-eval). Branch `p2/forms-plan` from `p2/ip`@b91ee33d.
## BOARD
S1 p mrg f 10737874 review P after fix (197 P); APPROVALS
S2 p mrg f 01b4bc46 review P; APPROVALS
S2w p mrg f b7e4ce92 security review P; APPROVALS
CR1 p todo f - orch-scheduled confidentiality rows; after S2
S3 p todo f - commands, uow seam; after S1, S2
S3s p todo f - form sources quality+permits; INSP C2, PTW C2
T01 t todo l - JSON Schema projection; after S1
T02 t todo f - runner model; after S1
T03 t todo f - views; after S3, CR1
T04 t todo f - read routes; after T03, X4 C2
T05 t todo f - tl form; after T03, X4 C2
T06 t todo f - MCP tools; after T03, S3, X4 C2
T07 t todo f - runner screen; after T02, T03
T08 t todo f - draft resume; after T05, T07
T09 t todo f - generator; after S3
T10 t todo f - walks; after T04, T06
T11 t todo f - demo; after T05-T10
T12 t todo l - docs and tour; after T11
T13 t todo f - insp_rules re-exports core; S1, INSP T00 merged
INTAKE I00 S6 S7c I01-I07, WEB W1 W2 B1-B4: README tables; specs later (no board rows yet)
## DEC
D1 2026-11-15 intake schema folded into S2 (ADR-0032 accepted): one schema gate; intake commands stay S7c (accept needs S3 seam); README, S2
D2 2026-11-15 format 2 field id `^[a-z][a-z0-9_]{0,31}$` so claim_* ids fit; format 1 keeps q<digits>; S1 spec, README risks
D3 2026-11-15 S1 does not wait for INSP T00: core writes format 1 rules itself; T13 re-exports later; S1 spec
D4 2026-11-15 no implementer ticket staged: every candidate reads S1 or S2 names (checklist 2); staged after they merge
D5 2026-11-15 S2 declares no `confidential` source: CR1 adds it with the subject rows before any reader exists
## SEC
(none yet; wave review over b91ee33d..<p2/ip head> at C4; rows in README)
## OPEN
Q1 spawn S1 and S2 together? S1 light, S2 heavy; PTW-S1 building (max 2 heavy runs) needs orch raised r1
Q2 numbering: allocator event for submission number at submit not first save; S2 reports it, S3 decides needs builder raised S2
Q3 webhook text check may fail (SR-X1 F3 open): then a fix piece needs orch raised S2
## NEXT
1. Orch: APPROVALS lines for S1 (core interface) and S2 (schema, words, settings, svc:intake); dispatch S1 and S2 (staggered).
2. After S1 and S2 merge (C1): round 2 writes CR1 brief, S3 spec, T01, T02, T13 tickets (T13 needs INSP T00 merged).
3. After INSP C2 and PTW C2: S3s spec. After X4 C2: T04-T06 tickets.
4. INTAKE specs after S3 and QR C2; WEB specs after C2.
## REFS
Provided test: docs/tickets/P2-FORMS/provided/S1_test_forms_rules.py (ruff format, ruff check clean; pyright only reports
the unresolved tl_core.forms import until S1 merges). Copy byte-identical to packages/tl-core/tests/test_forms_rules.py.
Specs: docs/tickets/P2-FORMS/S1-forms-contract-and-rules.md, S2-forms-schema.md.
## TRAPS
Provided tests fail `just check` where they land (E501, ruff format, pyright): run `uv run ruff format <f>`, `ruff check <f>`, `pyright <f>` before commit; wrong-type calls carry `# pyright: ignore[reportArgumentType]`.
Combined schema gates OOM on 16 GB: S2 gate is five runs. Provided test never run; first run is the S1 gate.
