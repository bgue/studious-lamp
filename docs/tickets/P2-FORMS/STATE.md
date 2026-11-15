# P2-FORMS STATE  r=2 base=f137cca7 C=C1 ck=0 gate=n/a wt=/home/user/wt/forms-plan
Plan `docs/tickets/P2-FORMS/README.md` (plan-checked via forms-eval). Branch `p2/forms-plan`, merged with `p2/ip`@f137cca7 (S1, S2, S2w in).
C1 reached: S1 and S2 merged with APPROVALS. Round 2 wrote S3, CR1, T01, T13, T14.
## BOARD
S1 p mrg f 10737874 review P after fix; APPROVALS
S2 p mrg f 01b4bc46 review P; APPROVALS
S2w p mrg f b7e4ce92 security review P; answers omitted from webhook bodies
S3 p mrg f 38c22c8e security review P; APPROVALS
CR1 p mrg f 600591e3 security review P after fixes; APPROVALS
CR1 p stg f - conf rows, own class, author-only draft; after S3
T14 t stg f - webhook scenario rows + envelope required fix
T01 t stg f - JSON Schema projection (full: no provided test)
T13 t stg f - insp_rules re-exports core validators
S3s p todo f - form sources quality+permits; INSP C2, PTW C2
T02 t todo f - runner model; needs a provided test first
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
INTAKE I00 S6 S7c I01-I07, WEB W1 W2 B1-B4: README tables; specs later (no board rows yet)
## DEC
D1 2026-11-15 intake schema folded into S2 (ADR-0032 accepted); intake commands stay S7c; README, S2
D2 2026-11-15 format 2 field id `^[a-z][a-z0-9_]{0,31}$` so claim_* ids fit; S1 spec
D3 2026-11-15 S1 core writes format 1 rules itself; T13 re-exports later; S1 spec
D4 2026-11-15 no ticket staged before S1/S2 merged (checklist 2); T01, T13, T14 staged r2
D5 2026-11-15 S2 declares no `confidential` source: CR1 adds it with the subject rows
D6 2026-11-15 numbering at submit: record created at first save with key null, `allocate_key` + `Record.Updated` key at submit (projector supports it); discarded draft takes no number; S3 spec (answers S2 Q2)
D7 2026-11-15 submissions are project scope only in v1; no company FRM pattern; templates are company scope; S3 spec, Q4
D8 2026-11-15 the seam `tl_core/services/nested.py` runs only module ProposableCommands, never core, workflow, dispatch, action or setting commands; S3 spec (answers F3)
D9 2026-11-15 template versions are records; revise = new Draft n+1; publish does not retire the predecessor; Draft always clean; S3 spec
D10 2026-11-15 general SaveFormDraft/SubmitForm take only general, Published templates; existing draft may finish after retire; S3 spec
D11 2026-11-15 refusal order: project, hidden subject BEFORE answers, template, own draft, version, save bound, answers; S3 spec
D12 2026-11-15 T14 carries the envelope fix (generator drops omit slots from detail.required; ledger payloads and compat untouched) because the contract schema test would fail on Template.Created, Template.Edited, IntakeCode.Issued once the scenario delivers them (S2w Open 1); T14 spec
D13 2026-11-15 CR1 follows S3 (both edit forms module.py); CR1 is the only forms piece in confidentiality.py (F8); answer_class also governs when a subject exists (own-class notion); CR1 spec
D14 2026-11-15 T01 review is full, not lite: no provided test exists (skill rule 5); README row said lite
## SEC
(wave review over b91ee33d..<p2/ip head> at C4; rows in README)
F-S3a open  agent-proposed answers sit in `cur_proposals.command_json` (Proposal.Created): S3 reports which readers filter it; Q5
F-CR1 open  draft read by author alone, own-class rule, intake rows: CR1 tests five readers
## OPEN
Q3 closed r2: S2w omits the slots; T14 fixes the envelope schema (D12)
Q4 submissions with no project (company-wide toolbox talk): default project only in v1 (D7); a company FRM block needs a schema line and APPROVALS needs owner raised S3 round
Q5 do proposal rows (`command_json`) hold answer text readable beyond the proposer: wave-review row or a fix piece after S3 report needs orch raised S3 round
## NEXT
1. Orch: APPROVALS for S3 (core interface: seam; security: drafts, numbering at submit) and CR1 (security, owner); dispatch S3 and workflow {T14} now.
2. After S3 merged: dispatch CR1 (orch confirms no other piece holds confidentiality.py; builder merges p2/ip first).
3. Next free slot: workflow {T01, T13} (staged, branches named in the tickets). Heavy runs at most 2 at once.
4. Round 3: T02 provided test (runner model: steps, back, skip hidden, review, confirm) then ticket; T09 after S3; T03 after S3 and CR1.
5. S3s spec after INSP C2 and PTW C2. T04-T06 wait for X4 C2 (not on trunk).
6. INTAKE specs after S3 and QR C2; WEB specs after FORMS C2.
## REFS
Specs: docs/tickets/P2-FORMS/{S1,S2,S2w,S3,CR1}-*.md. Tickets: T01-json-schema-projection.md, T13-insp-rules-reexport.md, T14-webhook-scenario.md.
Reports: docs/reports/P2-FORMS/{S1,S2,S2w}.md (S2 report holds the names table for S3, S6, S7c). Provided tests: docs/tickets/P2-FORMS/provided/.
No provided test this round: S3 and CR1 name their tests; T01 and T14 carry behaviours, T13 uses the merged T00 test.
## TRAPS
Provided or added tests must be lint-clean where they land: `ruff format`, `ruff check`, strict `pyright` over tests (`just check` runs it); wrong-typed calls carry `# pyright: ignore[...]`.
Statement-count tests ignore BEGIN, COMMIT, ROLLBACK. Schema gates run per file group (combined runs OOM on 16 GB; S2 gate was five runs). `uv run` in this worktree
lacks sqlalchemy (venv stripped by a `uv sync` without `--all-packages`): builders run `uv sync --all-packages` first.
Contract scenario (`tests/webhooks/scenario.py`) is shared with `tests/parity/test_webhooks_parity.py` and tl-tui `test_domain_plain.py`: pins move with it.
