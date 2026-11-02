# P2-I3 STATE  r=4 base=3da7b71 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i3
## BOARD
S1 p mrg f 485f3b4 schema merged; APPROVALS logged
S2 p mrg f af76b84 package + pins; e543b97 adds tl-mod-legacy dep + uv.lock; C1 done
T01a t mrg l 8aa58ed samples (50 items, 9 locations, 15 PO lines), 26 checks
S3 p mrg f 658c452 receipts, movements, actions, commands, tl_api glue; b21676a; 2s accepted by orch
T01b t mrg l 6b3e9c7 loaders mat-*; merge 3da7b71 (p2/i3 head at r4 start), ck0
S4 p stg f - RE-SCOPED r4: mto target + documents reverse hook + mapping via registry; branch p2/i3-s4-mto @c3398e0 (merge p2/i3 in first); spec S4-mto-publish.md
T03 t stg f - materials_reserved check; ticket T03-readiness.md; branch p2/i3-t03-readiness
T04a t stg f - 9 API read routes; ticket T04a-api-reads.md; branch p2/i3-t04a-api-reads
T04b t todo f - client methods; needs T04a
T05 t todo f - CLI tl mat + reports.py (+ /reports/{name} route); needs S4
T06a t todo f - stock screen + movement log; needs T04b
T06b t todo f - receipt log; T06e entry form; T06c library+locations; T06d mto log (after T06a / S4)
T07 t todo f - MCP tools; needs T04a. T08 t todo l - sim; needs T04b, T07
T11 p todo f - tests + mutants of S1-S4; at C3 (Sonnet). T09 demo (needs P2-I1 merged); T10 docs lite
## DEC
D1 2026-11-01 owner policy: tests at T11 (C3), pieces leave dev/accept/P2-I3/<id>.py + smoke, no pytest, no security review, tour at C4
D2 2026-11-01 UOM: S1 adds code list StockUom (EA SET BOX ROLL L m kg lb m3) to co.acme.materials@1.0.0; UnitOfMeasure has no EA (Q1 answered by orch)
D3 2026-11-01 code lists fixed in S1: ItemCategory 15, LocationKind 5, ConditionCode 4, MovementReason 7; samples paste the same lists
D4 2026-11-01 T01 split T01a samples / T01b loaders; ticket total 16, no PLANCHK
D8 2026-11-01 S2: stored `available` (projector writes on_hand-reserved); quantities Decimal in code (no SQL arithmetic)
D10 2026-11-01 RecordPoLine auto-adopts the ProjectItem; one root per project; ReviseLocation cannot re-parent
D13 2026-11-01 S2 review accepted: hand-written load targets; tl-mod-legacy dep; underscore target names materials_item_master/_location/_po_line
D14 2026-11-01 F4 glue (MATERIALS_COMMANDS, error rows, API_COMMANDS_OF pin) landed inside S3; now on p2/i3
D15 2026-11-01 four MTO error classes already in materials errors.py (S4 adds no ServiceError)
D17 2026-11-01 T01b mapping text kept as constants in loaders/materials.py (no mappings/ dir)
D19 2026-11-01 merge notes: openapi lives at docs/reference/openapi.json (regenerate after S4 and T04a, `python -m tl_api.openapi`); S3 RULES reads S4's MtoRule rows by shape
D20 2026-11-02 r4 orch accepted S3 2s (subjects not rewritten; rules.py waived; receipt line item must equal PO line item = rule) and T01b esc (include_confidential to bronze ok: materials sources carry no class; raw system count in dev script ok)
D21 2026-11-02 r4 S3 F3 LO (receipts missing_mtr filtered after LIMIT) was already fixed in SQL at 658c452 (S3 report 2a): nothing left for T04a. F3-info (mto_lines short_only scans all lines before limit) is a one-line report note in T04a; views.py untouched (D8 forbids SQL arithmetic)
D22 2026-11-02 r4 orch APPROVES the documents change under P2-Q10 (interface change; APPROVALS line at merge): S4 spec decision 5 = (a) optional reverse hook on PublishTarget used by publish.py compensation, (b) check_mapping accepts any publish_targets() name, mapping fields from the target, (c) schemas.py target_kind str. Generic, no materials import in documents. Replaces D16/Q4
D23 2026-11-02 r4 T04a guard is `document.read` (as routes/cost.py), not a new action: `materials.view` is the read role and AGENT_ACTIONS lives in tl_core.auth. Five-reader walk over classified materials records goes to T11 (D1); T04a only raises MIN_ROUTES and proves plumbing (no viewer passed)
D24 2026-11-02 r4 batch S4 + T03 + T04a: T03 and S4 both add a pyproject table (readiness_checks / publish_targets): keep both at merge; S4 and T04a both regenerate docs/reference/openapi.json: regenerate at merge. T05 waits for S4 (reports and mto verbs); T07 and T04b follow T04a
## SEC
(none; Sec rows S1-S4, T03, T04a, T07 recorded in spec §9, review only if the owner asks)
## OPEN
Q3 RejectReceipt user vs superuser: spec default user (owner decisions 15); no action needed owner raised spec §11
Q5 S3 report asks: reserve check is literal `reserved + qty <= line qty` (issued not added) while coverage counts both; `by_module` loosens nothing; Adopt on an ItemMaster is a project word at company scope, so a plain user is never offered it (row may belong on ProjectItem). Defaults kept; T11 pins them; veto needs orch raised S3
## NEXT
1. Orch: merge p2/i3 into p2/i3-s4-mto (c3398e0, report-only commit), then run S4 (builder, full), T03 and T04a (full) through ticket-batch-v2. New branches T03 and T04a from the r4 state commit.
2. r5 after the three mrg: T04b (client methods over T04a routes), T05 (CLI + reports.py + /reports/{name} route; needs S4 for `tl mat mto`), T07 (MCP read tools + propose_reservation; after T04a). Run the Haiku checklist on each; commit interfaces first.
3. Then T06a, then T06b/c/d/e; T08 after T04b and T07.
4. Registry glue by supervisor, last, after P2-I1 merges: add_typer for tl mat, MCP_ACTIONS, nav entry, MCP tool registration, pinned lists; regenerate.
5. C3: T11 spec (spec §9 tests list; mutant guards in the S2/S3/S4 reports), then T09 (needs P2-I1 merged), T10.
6. Seed ledger .accept/p2-i3.db is built by dev/accept/P2-I3/S3.py --keep (untracked, gitignored); T03, T04a, T05, T06 read it; rebuild after a schema change.
## REFS
Spec docs/build-spec/specs/m4-materials.md §9 (table), §10 (demo). Reports: docs/reports/P2-I3/{S1,S2,S3,T01a,T01b}.md; S4 Blocked report on branch p2/i3-s4-mto (worktree /home/user/wt/i3/s4, c3398e0).
Mutation guards for T11: S2 limits.py:27, handlers/locations.py:172 and :244, targets.py:342, projectors/stock.py:216 and :211; S3 handlers/receipts.py:850 (MTR), handlers/movements.py:389 (negative balance), :449 (reserve over line qty), :385 (consumable cost code), commands.py:104 (word of AdjustStock); S4 guards listed in its spec.
S3 facts: receipt commands take stream_id (+expected_version for Accept); `Movement` has from_location/to_location codes; Accept needs state Inspected; `RULES` rows read by shape (record_type|type, condition, label, command|command_name, word); `Rule` lives in actions.py; ids for MTOLine samples are 27 chars (fixtures only).
Seed ledger facts: project:P123, receipt P123-RCPT-0001 (heat H-7781, MTR attached), lots @1 @2, MTO ISO-1234@A/MTO 3 lines for awp.CWP P123-CWP-PIP-0001, actors user:materials-super, user:plain.
Specs/tickets this round: docs/tickets/P2-I3/{S4-mto-publish,T03-readiness,T04a-api-reads}.md.
## TRAPS
New worktrees: `uv sync --all-packages` first; pyright needs NODE_OPTIONS=--max-old-space-size=6144 (both in every acceptance). Worktree /home/user/wt/p2-i3 only; never /home/user/studious-lamp. dev/tests/ is outside testpaths (use tests/tools/). Never delete /tmp/pytest-of-root, never pkill. `just check` takes >120 s: background it. Do not rm -r dev/accept (tracked W0 scripts). P2-I1 and P2-WEB1 run beside: registries (tl_api/{auth,app,commands}.py, pyproject.toml, uv.lock, docs/reference/openapi.json) regenerate on merge, M4 merges last. A load target name cannot hold a dot. SQLite returns NUMERIC as float: read Decimal(str(x)). A reused worktree keeps its old base: check `git rev-list --left-right --count p2/i3...HEAD` before starting (p2/i3-s4-mto is behind by S3, T01b). A new dir under packages/tl-modules/ without a pyproject.toml breaks every uv run. A SQLite open_uow takes BEGIN IMMEDIATE on entry (barrier before the with). `bronze` needs include_confidential and a LakeConfig for internal runs.
