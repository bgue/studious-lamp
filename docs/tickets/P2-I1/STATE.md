# P2-I1 STATE  r=1 base=1b93a13 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p todo f - schema awp; spec staged r1; gate owner
S3 p todo f - package, WBS, path, CWA cmds; after S2
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
## SEC
(none; review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
Q1 P2-Q10 delegation: orch approves S2 schema merge and logs APPROVALS at merge needs orch raised r1
## NEXT
1. r2: verify S2 merged (git log), then write S3 (package, entry points, WBS/path/CWA handlers, rollup.request only, stubs of targets.py and views.py).
2. r2: also S5 only if S3 is merged; else wait. Prefer r3 for S4+S5+T02 together (disjoint paths).
3. Each piece spec: acceptance script dev/accept/P2-I1/<id>.py, no pytest; S4 leaves .accept/p2-i1.db (WBS, 4 CWAs, path v1, 6 CWPs).
4. Registry glue (AWP_COMMANDS splat, add_typer, MCP_ACTIONS, nav entry) is supervisor glue, <= 50 lines, at C2; WEB1 touches the same registries: regenerate, never hand-merge.
5. Twin web tickets for the CWP and CWA registers, WBS tree and path, packages belong to WEB1 after C2.
6. T11 lists its test files in spec §10; write T11 spec at C2.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; wave plan phase2-wave-plan.md; W0 trunk acceptance dev/accept/P2-W0/*.py (style for scripts); piece spec example docs/tickets/P2-W0/S4-load-publish-targets.md.
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes >120 s: run in background. Entry-point metadata is read at install time: `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill.
