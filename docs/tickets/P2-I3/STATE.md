# P2-I3 STATE  r=1 base=3ed66af C=0 ck=- gate=n/a wt=/home/user/wt/p2-i3
## BOARD
S1 p stg f 3ed66af schema piece, human gate (95), branch p2/i3-s1-schema
T01a t stg l 3ed66af sample CSVs; split from T01; branch p2/i3-t01a-samples
S2 p todo f - package, library, locations, po lines; needs S1 + W0-B2 (merged)
S3 p todo f - receipts, movements, actions; needs S2
S4 p todo f - mto publish target; needs S2; beside S3 (disjoint files)
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
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q1 UOM list StockUom instead of UnitOfMeasure (D2): confirm or give another list needs orch raised S1
Q2 ADR-0022 (movements as events, P2-Q5 B) is not in docs/adr yet (0021 is last); S1 reads it if present, merge needs it needs orch raised S1
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needs owner raised spec §11
## NEXT
1. Orch: run S1 + T01a through ticket-batch-v2; S1 is the 95 gate: approve under P2-Q10 after review, log APPROVALS.
2. r2 after S1 mrg: write S2 (package, handlers items/locations/po_lines, targets, views, mto.py stub, entry points) and T01b; guards in spec §9.
3. r2 also: S4 spec (only mto.py, handlers/mto.py, pyproject entry) once S2 spec exists so they can run beside S3.
4. r3 after S2 mrg: S3 spec (receipts, movements, actions, commands, api.py) and S4 dispatch; T03, T04a ticket drafts (interfaces pasted from S3).
5. At C2: T04b..T08 tickets; registry glue (MATERIALS_COMMANDS splat, add_typer, MCP_ACTIONS, nav) by supervisor, last, after P2-I1 merges.
6. C3: T11 spec (tests list spec §9) then T09, T10. Then merge-last regeneration of pinned lists.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Wave plan phase2-wave-plan.md §3. Analog acceptance: dev/accept/P2-W0/OC-S1.py. Access words already on trunk: schema/settings/access-words.yaml (materials.*), platform.yaml key materials.receipt.mtr_required_categories (default []). W0-B2 targets on trunk.
## TRAPS
Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Tagging a core class changes generated/models.py. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, openapi.json) regenerate on merge, M4 merges last.
