# P2-I3 STATE  r=2 base=ebd7dc9 C=0 ck=- gate=n/a wt=/home/user/wt/p2-i3
## BOARD
S1 p mrg f 485f3b4 schema merged; APPROVALS logged; C1 half
S2 p disp f 842ecfb package spec; branch p2/i3-s2-package; skeleton pyproject at 2aef8fb
T01a t disp l ebd7dc9 data done 7ac62fc; merge p2/i3 into branch, run acceptance, lite review
S3 p todo f - receipts, movements, actions, commands; needs S2 mrg
S4 p todo f - mto publish target; needs S2 mrg; beside S3 (disjoint files)
T01b t todo l - mappings + loaders mat-items/locations/po-lines; needs S2, T01a
T03 t todo f - materials_reserved check; needs S3
T04a t todo f - API read routes + walk entries; needs S3
T04b t todo f - client methods; needs T04a
T05 t todo f - CLI tl mat + reports.py; needs S3, S4
T06a t todo f - stock screen + movement log; needs T04b
T06b t todo f - receipt log; T06e entry form; T06c library+locations; T06d mto log (after T06a / S4)
T07 t todo f - MCP tools; needs T04a. T08 t todo l - sim; needs T04b, T07
T11 p todo f - tests + mutants of S1-S4; at C3 (Sonnet). T09 demo (needs P2-I1 merged); T10 docs lite
## DEC
D1 2026-11-01 owner policy applied: tests at T11 (C3), pieces leave dev/accept/P2-I3/<id>.py + smoke, no pytest, no security review, tour at C4
D2 2026-11-01 UOM: UnitOfMeasure (closed, co.acme.standards) has no EA; S1 adds code list StockUom (EA SET BOX ROLL L m kg lb m3) to co.acme.materials@1.0.0; spec says UnitOfMeasure; not edited; orch confirm (Q1)
D3 2026-11-01 code lists fixed in S1: ItemCategory 15 values, LocationKind 5, ConditionCode good/damaged/wrong_item/nonconforming, MovementReason 7 (S1 decision 1); samples paste the same lists
D4 2026-11-01 T01 split: T01a samples (round 1, no S2 needed), T01b mappings+loaders (after S2); ticket total 16, no PLANCHK (spec plan-checked)
D5 2026-11-01 dispatch rule: nothing else in spec §9 can start before S1 (all need generated models or S2); round-1 batch is S1 + T01a only
D6 2026-11-01 T01a acceptance script is written by the implementer from the listed assertions (own diff cap forbids a provided one ~107 lines)
D7 2026-11-01 commit attribution lines: used the harness's lines for this session (Sonnet 5.5); tickets name no model, say "attribution lines your harness requires"
D8 2026-11-01 r2 orch decisions into S2 spec: stored `available` (projector writes on_hand-reserved); quantities Decimal in code (no SQL arithmetic); OC-S1.py pin extension and extra S1 columns accepted
D9 2026-11-01 r2 own diff: skeleton package pyproject (no entry points) + root uv source + uv.lock, 2aef8fb, so T01a unblocks now instead of after S2
D10 2026-11-01 r2 RecordPoLine auto-adopts the ProjectItem (module-written); one root per project; ReviseLocation cannot re-parent (S2 spec decisions 4-6)
D11 2026-11-01 r2 T01a Q2 4471-4 accepted, Q3 depth 4; acceptance of every item carries `uv sync --all-packages` + NODE_OPTIONS=--max-old-space-size=6144
D12 2026-11-01 weekly capacity near stop line: r2 batch is S2 + T01a only (nothing else is independent of S2)
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needs owner raised spec §11
(Q1 StockUom, Q2 ADR-0022: closed r2, S1 merged)
## NEXT
1. Orch: run S2 (builder) and T01a (lite) through ticket-batch-v2. T01a: merge p2/i3 into its branch first. S2 needs no human gate (no schema), review full.
2. r3 after S2 mrg: write S3 spec (receipts, movements, actions, commands.py append, api.py post_movements; views receipts/mto_lines) and S4 spec (only mto.py, handlers/mto.py, pyproject entry); dispatch both beside each other.
3. r3 also: T01b (mappings + loaders over S2 targets; interfaces then in tree), T03/T04a drafts from S3 interfaces.
4. At C2: T04b..T08 tickets; registry glue (MATERIALS_COMMANDS splat, add_typer, MCP_ACTIONS, nav) by supervisor, last, after P2-I1 merges.
5. C3: T11 spec (tests list spec §9) then T09, T10. Then merge-last regeneration of pinned lists.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Wave plan phase2-wave-plan.md §3. Analog acceptance: dev/accept/P2-W0/OC-S1.py. Access words already on trunk: schema/settings/access-words.yaml (materials.*), platform.yaml key materials.receipt.mtr_required_categories (default []). W0-B2 targets on trunk.
## TRAPS
New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (put both in every acceptance). Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Tagging a core class changes generated/models.py. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, openapi.json) regenerate on merge, M4 merges last.
