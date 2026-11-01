# P2-I3 STATE  r=3 base=e543b97 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i3
## BOARD
S1 p mrg f 485f3b4 schema merged; APPROVALS logged
S2 p mrg f af76b84 package + pins; e543b97 adds tl-mod-legacy dep + uv.lock; C1 done
T01a t mrg l 8aa58ed samples (50 items, 9 locations, 15 PO lines), 26 checks
S3 p stg f - receipts, movements, actions, commands, tl_api glue; spec S3-receipts-movements.md; branch p2/i3-s3-receipts
S4 p stg f - mto target, AssignMtoLines; spec S4-mto-publish.md; branch p2/i3-s4-mto; beside S3 (disjoint)
T01b t stg l - loaders mat-*; ticket T01b-loaders.md; branch p2/i3-t01b-loaders; independent of S3/S4
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
D13 2026-11-01 r3 S2 review F1-F7 accepted by orch: hand-written load targets kept; tl-mod-legacy dep added (e543b97); underscore target names materials_item_master/_location/_po_line (spec, S2 ticket, T01a ticket text fixed); DRAFT_COMMAND_WORDS stopgap until S3; tests/webhooks/scenario.py override pinned
D14 2026-11-01 r3 F4 glue (MATERIALS_COMMANDS in tl_api/commands.py, error rows in tl_api/errors.py, "materials" in tests/services/test_module_role_seams.py API_COMMANDS_OF, openapi.json) is in S3 Allowed paths, so it lands with the commands it names; the two red pins turn green at S3 merge
D15 2026-11-01 r3 own diff: four MTO error classes appended to materials errors.py (MtoPublishRefusedError, MtoLineNotFoundError, MtoLineInUseError, WorkPackageNotFoundError) so S4 adds no ServiceError and S3 alone owns errors.py plus the tl_api rows
D16 2026-11-01 r3 documents gap: schemas.py:77 types target_kind Literal["tags","documents"], so no schema can name mto. S4 spec decision 5 widens it to str with a publish_targets() check (one documents file, openapi regen). Crosses a package interface (tiers 3 trigger): orch may veto at dispatch (Q4)
D17 2026-11-01 r3 T01b keeps mapping text as constants in loaders/materials.py (no mappings/ dir, no yaml files): the targets read grid columns by name and only hash mapping_text; keeps the ticket at 5 files
D18 2026-11-01 r3 weekly capacity 91%: batch is built to wait. Priority if only some can run: S3 first (blocks T03 T04a T05 and the glue), then S4, then T01b. Every item is independent of the others on disk; STATE and specs are complete for a fresh round after the reset
D19 2026-11-01 r3 merge notes for orch: merge S4 before T01b (both add a pyproject table next to load_targets: keep both); regenerate packages/tl-api/openapi.json after S3 and S4 are both in (python -m tl_api.openapi); S3 RULES must accept S4's MtoRule rows by shape (S4 report names the shape)
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needs owner raised spec §11
Q4 D16 widen documents target_kind Literal inside S4; veto at dispatch or accept needs orch raised r3
## NEXT
1. Orch (when capacity allows, <93%): run S3 and S4 (builders, full review) and T01b (lite) through ticket-batch-v2; order S3, S4, T01b. Branch from p2/i3 head (st commit of r3). Setup per item: uv sync --all-packages; NODE_OPTIONS=--max-old-space-size=6144 just check.
2. r4 after S3 and S4 mrg (C2 half): write T03 (readiness; S3 interfaces), T04a (API read routes over S3 views; walk entries), T05 (CLI + reports.py; needs S3, S4); T04b after T04a; T07 after T04a. Run the Haiku checklist on each; commit interfaces first.
3. After T04b: T06a, then T06b/c/d/e; T08 after T04b and T07.
4. Registry glue by supervisor, last, after P2-I1 merges: add_typer for tl mat, MCP_ACTIONS, nav entry, MCP tool registration, pinned lists; regenerate.
5. C3: T11 spec (spec §9 tests list; mutants guards listed in S2/S3/S4 reports), then T09 (needs P2-I1 merged), T10.
6. Seed ledger .accept/p2-i3.db is built by dev/accept/P2-I3/S3.py --keep (untracked, .accept/ gitignored by S3); T05 and T06 acceptance read it; rebuild it when a schema change lands.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Wave plan phase2-wave-plan.md §3. Analog acceptance: dev/accept/P2-W0/OC-S1.py, dev/accept/P2-I3/S2.py (ledger setup, event replay). Access words on trunk: schema/settings/access-words.yaml (materials.*), platform.yaml key materials.receipt.mtr_required_categories (default []). W0-B2 targets on trunk. Reports: docs/reports/P2-I3/{S1,S2,T01a}.md; S2 mutation guards for T11: limits.py:27, handlers/locations.py:172 and :244, targets.py:342, projectors/stock.py:216 and :211.
Specs this round: docs/tickets/P2-I3/{S3-receipts-movements,S4-mto-publish,T01b-loaders}.md. S2 facts S3/S4 use: reserve/unreserve/issue/scrap/adjust-out use from_location_id, receive/return/adjust-in use to_location_id; quantities Decimal; projector raises on a negative balance.
## TRAPS
New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (put both in every acceptance). Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Tagging a core class changes generated/models.py. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, openapi.json) regenerate on merge, M4 merges last. A load target name cannot hold a dot. SQLite returns NUMERIC as float: read Decimal(str(x)). A reused worktree keeps its old base: check `git rev-list --left-right --count p2/i3...HEAD` before starting. A new dir under packages/tl-modules/ without a pyproject.toml breaks every uv run. S1 samples of MTOLine.Defined.mto_id and .work_package_id are 27 characters, not ULIDs (fixtures only).
