# P2-FORMS STATE  r=3 base=8878427d C=C2 ck=0 gate=n/a wt=/home/user/wt/forms-plan
Plan `docs/tickets/P2-FORMS/README.md` (plan-checked via forms-eval). Branch `p2/forms-plan` merged with `p2/ip`@8878427d.
C2 reached for S3 and CR1 (S3s waits for INSP C2 and PTW C2). Round 3 wrote S7c, S6, W1, W2 specs and tickets T02, I02 (provided tests).
## BOARD
S1 p mrg f 10737874 review P; APPROVALS
S2 p mrg f 01b4bc46 review P; APPROVALS
S2w p mrg f b7e4ce92 answers omitted from webhook bodies
S3 p mrg f 38c22c8e seam + 11 commands; APPROVALS
CR1 p mrg f 600591e3 confidentiality rows, author rule; APPROVALS
S7c p mrg f 629257b5 security review P; APPROVALS; wave items: code_hash omit, CLI-only issue
T14 t disp f - webhook scenario rows + envelope fix; in flight
T13 t mrg f 033059de review P
T01 t stg f - JSON Schema projection; ready, branch exists
T02 t stg f - runner model; provided test T02_test_forms_runner.py
I02 t stg f - intake page render; provided test I02_test_intake_page.py
S7c p stg f - intake commands + tl_core/qr/codes.py (D15)
W1 p stg f - vendor SurveyJS MIT; owner licence line; free slot
S6 p todo f - public /i/ route; after S7c, I02; owner human gate
W2 p todo f - fill page; after W1, B1, T04, X4 on trunk
S3s p todo f - form sources quality+permits; INSP C2, PTW C2
T03 t todo f - views; deps S3, CR1 merged: stage next round
T09 t todo f - generator; dep S3 merged: stage next round
T04 t todo f - read routes via X4 hooks; X4 on trunk
T05 t todo f - tl form; X4 on trunk
T06 t todo f - MCP tools; X4 on trunk
T07 t todo f - runner screen; after T02, T03
T08 t todo f - draft resume; after T05, T07
T10 t todo f - walks; after T04, T06
T11 t todo f - demo; after T05-T10
T12 t todo l - docs and tour; after T11
I01 t todo f - poster label; after S7c
I03 t todo f - queue views + routes; after S7c
I04 t todo f - tl intake incl purge command (D19); after I03
I05-I07 t todo f - TUI log, walks, runbook+demo; after I03, S6
B1 t todo f - to_surveyjs; after W1, T01 (before W2)
B2-B4 t todo f - card open_path, draft resume, demo; after W2
## DEC
D1-D14 2026-11-15 recorded in earlier rounds (intake schema in S2; format 2 id pattern; numbering at submit D6; seam D8; T14 envelope D12); see S1-S3, CR1 specs.
D15 2026-11-16 I00 dropped: QR S2 not started, nothing to lift; S7c creates frozen pure `tl_core/qr/codes.py`; QR S2 must import it; S7c spec
D16 2026-11-16 server never sees an intake code: IssueIntakeCode takes code_hash; weak caller-chosen code accepted, noted for security review; S7c spec
D17 2026-11-16 accept takes the controller's completed command_type + command_args; stored body read once, only for the claim (no phone); S7c spec
D18 2026-11-16 accept deletes the body row and appends Purged in the same unit; reject keeps body to retention; S7c spec
D19 2026-11-16 purge = job kind + purge_due; only S6 intake.py and S7c accept delete body rows (repo test); scheduling is `tl intake purge` (I04) and runbook; S6 spec
D20 2026-11-16 stranger writes through a service (no command door), actor svc:intake, source intake:<code id>; S6 spec
D21 2026-11-16 limits count every request, before body read and code lookup, keyed on address and on hash of presented segment, bounded LRU; S6 spec
D22 2026-11-16 item id = ULID from sha256(code id : form key), receipt word from item id; double tap writes once; S6 spec
D23 2026-11-16 stored text NFC, control and bidi removed, canonical JSON <= 8 KB, HMAC under per-item salt kept in body row; S6 spec
D24 2026-11-16 /i/ headers and no cookie on every answer incl errors; own stylesheet /web/static/intake.css; auth open prefix /i/; S6 spec
D25 2026-11-16 access-log path redaction via tl_api/accesslog.py with prefix tuple (QR S3 appends /web/q/); S6 spec
D26 2026-11-16 not built in S6: controller feed card (count only), photo, captcha, fill-time, outbox; S6 spec
D27 2026-11-16 W2 reads through T04's X4 hook routes; forms names hooks in its own package only (not in IN_TREE_SURFACES); W2 spec
D28-D31 2026-11-16 W2 routes under /web/forms, JSON model block via tojson, plain-text renderer, policy unchanged, drafts via CR1 rule; W2 spec
D32 2026-11-16 W1 finding: neither npm tarball ships a LICENSE file; MIT from package.json and banners; licence text from upstream v3.2.5 sha256 ef2cef07; W1 spec
D33 2026-11-16 W2 consumes B1 (`to_surveyjs`); B1 runs after W1 and T01, before W2; README rows updated
## SEC
F-S3a fixed@600591e3 agent-proposed answers in cur_proposals.command_json now filtered (hidden_answer_templates); CR1 proofs
F-CR1 fixed@600591e3 security review P after fixes (activity feed, own class, author exemption)
F-S6 open (review row) public route: dead-code bytes, limits before read, no cookie, body only in forms_intake_body; at S6
F-S7c open (review row) D16 weak caller-chosen code; accept runs nested command as controller with holder
(wave review over b91ee33d..<p2/ip head> at C4; rows in README)
## OPEN
Q4 submissions with no project (company-wide toolbox talk): project only in v1 (D7); company FRM block needs schema line + APPROVALS; needs owner raised S3 round
Q6 QR supervisor must import tl_core/qr/codes.py (D15) and not write its own generate/hash; needs orch raised r3
Q7 forms clearance table (privileged class hides from all but author, CR1 Q4): owner decision pending; deferred
Q8 gate-pg of tests/confidentiality twin walk OOM/stall on Postgres (CR1 Q5): not told apart from base; needs orch raised CR1
Q9 owner: W1 licence line; S6 and S7c security APPROVALS; owner approves S6 human gate raised r3
## NEXT
1. Orch: dispatch S7c (builder) and workflow {T01, T02, I02} now (2 slots beside T13/T14); W1 next free slot (owner licence line before merge).
2. After S7c and I02 merged: S6 dispatch (owner APPROVALS first; not in the round of W2).
3. Round 4: stage T03 and T09 (deps merged); I01, I03 after S7c; B1 after W1 and T01.
4. When X4 on trunk: write T04-T06 against hooks (own package refs, D27); then W2 dispatch.
5. S3s spec after INSP C2 and PTW C2.
6. Tell QR supervisor: codes.py is S7c's (Q6); QR S2 imports it.
## REFS
Specs: docs/tickets/P2-FORMS/{S1,S2,S2w,S3,CR1,S7c,S6,W1,W2}-*.md. Tickets: T01, T02, T13, T14, I02 (`*-*.md`). Provided tests: docs/tickets/P2-FORMS/provided/ (S1, S2w, T02_test_forms_runner.py, I02_test_intake_page.py; both new ones ran green against a reference implementation, ruff clean).
Reports: docs/reports/P2-FORMS/{S1,S2,S2w,S3,CR1}.md (S2 names table; S3 seam and command table; CR1 rows). X4 interfaces: `git show p2/x4:packages/tl-core/src/tl_core/modules.py`, `p2/x4:tests/ext_demo/src/tl_mod_ext_demo/`.
## TRAPS
Provided or added tests lint-clean where they land (`ruff format`, `ruff check`, strict pyright over tests). Statement-count tests ignore BEGIN, COMMIT, ROLLBACK. Schema gates per file group.
Gate runner kills runs over about 10 minutes: S6 and S7c gates are split per file group. `uv sync --all-packages` first in a builder worktree (stripped venv).
Contract scenario `tests/webhooks/scenario.py` is shared (T14). `tl_web/app.py`: S6 (/i/) and W2 (/web/forms) never in one round. Downloaded npm tarballs are untrusted: fresh empty dir, `python -I`.
p2/x4 branched from an older base (591 files differ): read interfaces with `git show`, merge only when the orchestrator lands X4.
