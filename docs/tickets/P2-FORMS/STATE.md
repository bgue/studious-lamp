# P2-FORMS STATE  r=4 base=eb42d7dc C=C2 ck=0 gate=n/a wt=/home/user/wt/forms-plan
Plan `docs/tickets/P2-FORMS/README.md` (plan-checked via forms-eval). Branch `p2/forms-plan` merged with `p2/ip`@eb42d7dc.
C2 reached for S3 and CR1 (S3s waits INSP C2, PTW C2). Round 4 wrote B1, I01, I03, T03, T09 tickets (no provided tests: tests named in each ticket), refreshed S6 (D34-D36) and W2.
## BOARD
S1 p mrg f 10737874 review P; APPROVALS
S2 p mrg f 01b4bc46 review P; APPROVALS
S2w p mrg f b7e4ce92 answers omitted from webhook bodies
S3 p mrg f 38c22c8e seam + 11 commands; APPROVALS
CR1 p mrg f 600591e3 confidentiality rows, author rule; APPROVALS
S7c p mrg f 629257b5 security review P; APPROVALS; code_hash omit moved to S6
W1 p mrg f 56b007d0 vendored SurveyJS; licence APPROVALS
T13 t mrg f 033059de review P
T01 t mrg f f29ff533 review P after report fix
T02 t mrg f 376da6cb review P
I02 t mrg f 1f954d33 review P
T14 t disp f - webhook scenario; waits Postgres rerun (orch)
B1 t stg f - to_surveyjs; ticket B1-surveyjs-projection.md; dispatch r4
I01 t stg f - tl intake code issue|revoke; dispatch r4; base p2/ip
I03 t stg f - queue views, no hash or body leak; dispatch r4
T03 t stg f - views + form_for; dispatch r4
T09 t stg f - demo section forms; next batch (heavy child runs)
S6 p todo f - public /i/ route; spec refreshed D34-D36; owner human gate
W2 p todo f - fill page; spec uses SurveyUI.Model; after B1, T04, X4 on trunk
S3s p todo f - form sources quality+permits; INSP C2, PTW C2
T04 t todo f - read routes + ?as=jsonschema|surveyjs; X4 hooks (p2/ip-r3)
T05 t todo f - tl form; X4 hooks
T06 t todo f - MCP tools; X4 hooks
T07 t todo f - runner screen; after T02, T03
T08 t todo f - draft resume; after T05, T07
T10 t todo f - walks; after T04, T06
T11 t todo f - demo; after T05-T10
T12 t todo l - docs and tour; after T11
I03r t todo f - /forms/intake/ routes; after I03, X4 hooks
I04 t todo f - tl intake ls|show|accept|reject|purge; after I01, I03
I05-I07 t todo f - TUI log, walks, runbook+demo; after I03, S6
I08 t todo f - poster label; after I01, QR S2
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
D34 2026-11-16 code_hash of IntakeCode.Issued gets `tl:webhook: omit` (one schema line, S2w mechanism) inside S6, owner's APPROVALS line names it; never in a read view; S6 spec
D35 2026-11-16 per-code limiter keyed on hash of normalised code (raw segment cut to 64 bytes when malformed), same function and 429 for live, dead, malformed; S6 spec
D36 2026-11-16 caps count bytes: body read to 8193 bytes, stored canonical JSON <= 8192 UTF-8 bytes, body_bytes = that length (S2 review F1); S6 spec
D37 2026-11-16 I01 is `tl intake code issue|revoke` (CLI makes the code, prints once, no --code option); poster label moves to I08 (needs QR S2); I04 loses issue and revoke
D38 2026-11-16 I03 split: views now (I03), signed-in routes later (I03r, needs X4 hooks, base p2/ip-r3); views never select code_hash, body_mac, salt
D39 2026-11-16 B1 shape: panels per section, photo left out and listed by surveyjs_unsupported, no min/max (out-of-range number is valid), visibleIf strings pinned; W2 uses SurveyUI.Model

## SEC
F-S3a fixed@600591e3 agent-proposed answers in cur_proposals.command_json now filtered (hidden_answer_templates); CR1 proofs
F-CR1 fixed@600591e3 security review P after fixes (activity feed, own class, author exemption)
F-S6 open (review row) public route: dead-code bytes, limits before read, no cookie, body only in forms_intake_body; at S6
F-S7c open (review row) weak caller-chosen code: closed by I01 (CLI always new_code, no --code); code_hash webhook omit + no read view: S6 D34, I03; limiter key D35; byte caps D36
(wave review over b91ee33d..<p2/ip head> at C4; rows in README)
## OPEN
Q4 submissions with no project (company-wide toolbox talk): project only in v1 (D7); company FRM block needs schema line + APPROVALS; needs owner raised S3 round
Q6 QR supervisor must import tl_core/qr/codes.py (D15), not write its own; needs orch raised r3
Q7 forms clearance table (privileged class hides from all but author, CR1 Q4): owner decision pending; deferred
Q8 gate-pg of tests/confidentiality twin walk OOM/stall on Postgres (CR1 Q5): not told apart from base; needs orch raised CR1
Q9 owner approves S6 human gate (APPROVALS line incl. D34 schema line) before merge; build may proceed needs owner raised r3
Q10 I01 adds `intake` group to tl_cli/main.py on p2/ip; F2 hook branch p2/ip-r3 may add one too: conflict at merge goes to a supervisor round needs orch raised r4
## NEXT
1. Orch: dispatch workflow {B1, T03, I03} (p2/ip) and I01 (p2/ip); 3 slots, T14 waits Postgres rerun.
2. Round 5: stage T09 dispatch; S6 dispatch when owner approves (not in the round of W2); I04 after I01+I03.
3. When X4 hooks are on p2/ip (or on base p2/ip-r3): write T04-T06 (T04 names `?as=jsonschema|surveyjs`), I03r; then W2 dispatch (B1 merged first).
4. S3s spec after INSP C2 and PTW C2.
5. Tell QR supervisor: codes.py is S7c's (Q6); QR S2 imports it; I08 waits QR S2.
## REFS
Specs: docs/tickets/P2-FORMS/{S1,S2,S2w,S3,CR1,S7c,S6,W1,W2}-*.md. Tickets: T01, T02, T03, T09, T13, T14, B1, I01, I02, I03 (`*-*.md`). Provided tests: docs/tickets/P2-FORMS/provided/ (S1, S2w, T02, I02).
Reports: docs/reports/P2-FORMS/{S1,S2,S2w,S3,CR1,S7c,W1,T01,T02,T13,I02}.md. X4 interfaces: `git show p2/x4:packages/tl-core/src/tl_core/modules.py`, `p2/x4:tests/ext_demo/src/tl_mod_ext_demo/`.
## TRAPS
Provided or added tests lint-clean where they land (`ruff format`, `ruff check`, strict pyright over tests). Whole-repo pyright OOMs on this box: scoped pyright over touched dirs. Statement-count tests ignore BEGIN, COMMIT, ROLLBACK.
Gate runner kills runs over about 10 minutes: split per file group. `uv sync --all-packages` first in a builder worktree. Demo-project tests run child processes (heavy, one at a time).
Contract scenario `tests/webhooks/scenario.py` is shared (T14). `tl_web/app.py`: S6 (/i/) and W2 (/web/forms) never in one round. Downloaded npm tarballs untrusted: fresh dir, `python -I`.
SurveyJS class is SurveyUI.Model. p2/x4 branched from an older base: read with `git show`, merge only when the orchestrator lands X4.
