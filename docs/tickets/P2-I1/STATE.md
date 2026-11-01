# P2-I1 STATE  r=2 base=1b93a13 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p mrg f 99ad743 schema awp merged; APPROVALS logged; F1 F2 LO
S3 p stg f - spec staged r2; also folds F2 index drop and Q1 feed fix; sch gate
S4 p todo f - CWP, packages, RULES; after S3
S5 p todo f - rollup job; beside S4
T02 t todo f - load targets; after S3
T01 t todo l - samples, mappings, loaders; after T02
T10 t todo f - read views; after S4
T03a t todo f - API routes; after T10
T03b t todo f - client methods; after T03a
T04 t todo f - CLI and reports; after S5, T10
T05a t todo f - CWP register; after T03b
T05b t todo f - WBS tree, CWA register; after T05a
T05c t todo f - path, package logs; after T05a
T06 t todo f - MCP tools; after T03a
T07 t todo l - sim AwpDesk, actor; after T03b, T06
T11 p todo f - tests + capped mutants; after all
T08 t todo f - demo; after T11
T09 t todo l - docs; after T04, T05
## DEC
D1 2026-11-01 round 1 file names: S2 S3 S4 S5 T01..T11 as spec §10 ids; table in README.md; report path = file id
D2 2026-11-01 no model names in committed files: tier field reads builder/implementer; trailer = harness trailer, not discussed
D3 2026-11-01 first batch is S2 alone: every other row of spec §10 depends on S2 or later (S3 needs generated models)
D4 2026-11-01 owner policy: tests at T11 (C3), tour once at C4, no security review; Sec rows recorded not run
D5 2026-11-01 access words and awp.* keys already on trunk (schema/settings/access-words.yaml lines 10-19); S2 adds none
D6 2026-11-01 Q1 feed: 8 awp no-card events added to POLICY_EVENT_TYPES in tl_core/feed/cards.py by S3 (builder may pick smaller safe change)
D7 2026-11-01 r2 batch is S3 alone: T02/S4/S5 depend on S3; no ticket has all deps merged; capacity near stop line
## SEC
F1 LO fixed@- S2 report 65>60 lines; waived
F2 LO open S3 drops redundant ix_scope_code/ix_scope_package (wbs cwa external_package); regen
(review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
(none open; Q1 closed D6, P2-Q10 S2 approved and logged)
## NEXT
1. r3 (after S3 merged, schema line in APPROVALS for the index edit): S4 + S5 + T02 together (disjoint paths); S5 needs S3 only.
2. S4 leaves .accept/p2-i1.db (WBS, 4 CWAs, path v1, 6 CWPs); S4 extends AWP_COMMANDS and RULES that S3 creates.
3. r4: T10 (after S4), T01 (after T02). Each piece spec: acceptance script dev/accept/P2-I1/<id>.py, no pytest.
4. Registry glue (AWP_COMMANDS splat, add_typer, MCP_ACTIONS, nav entry) is supervisor glue <= 50 lines at C2; WEB1 shares the registries: regenerate, never hand-merge.
5. Twin web tickets for CWP/CWA registers, WBS tree, path, packages belong to WEB1 after C2.
6. T11 lists its test files in spec section 10; write T11 spec at C2.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; wave plan phase2-wave-plan.md; W0 trunk acceptance dev/accept/P2-W0/*.py (style for scripts); piece spec example docs/tickets/P2-W0/S4-load-publish-targets.md.
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes >120 s: run in background. Entry-point metadata is read at install time: `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill.
