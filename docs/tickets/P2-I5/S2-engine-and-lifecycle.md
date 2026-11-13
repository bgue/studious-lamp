# P2-I5-S2 — rules-of-credit engine, progress commands, IWP field lifecycle

Status: ready (after S1 is merged and the plan check is answered)
Tier: builder
Kind: piece
Review: full
Labels: core, commands
Depends on: S1 (and P2-INT C2 on the base)
Branch: `p2/i5-s2-engine`
Worktree: `/home/user/wt/i5-s2`
Approver: orchestrator reads the diff for the state-move access words (P2-Q10); no schema in this piece

## Goal
After this piece earned progress per IWP is computed from linked record states through the project's rules-of-credit edition, scope items move
state by command, quantities without records are entered by hand, and an IWP can be started and marked field complete. `S3`, `S4`, `S5` and the
read tickets start from the merged functions. This piece owns `module.py`, `names.py` and the `AWP_COMMANDS` edits of I5.

## Brief references (pasted)
- Progress earned from linked record states through rules of credit; manual entry only for commodities without records (`field-work-packaging.md`).
- IWP workflow (exists): Issued -> In progress is `start`; In progress -> Field complete is `complete`, guarded by `no_open_blocking_constraints`.
- Scope item workflow (exists): `install`, `return`, `verify`, `void`; moves are commands of the awp module (`by_module`).
- Edition: setting `awp.rules_of_credit.set` holds `package@version` of an adopted schema package (project, company, platform); empty means `co.acme.awp@1.1.0`; the rules are the package's `rules_of_credit` section (S1); progress already recorded keeps its edition.

## Interfaces to build (names fixed here; ADR-0027 and ADR-0024 apply)
```python
# tl_mod_awp/progress/engine.py  (pure, no I/O except the connection it is handed)
def edition_for(conn, scope: str) -> Rules                        # setting, else co.acme.awp@1.1.0, read from the adopted package content; unknown or not adopted -> RulesOfCreditError
def earned_fraction(conn, iwp_id: str, *, viewer=None) -> Earned  # Earned(pct: Decimal 1 dp <= 100.0, edition: str, items: list[ItemEarned], notes: list[str])
# tl_mod_awp/commands.py additions (models, all extra="forbid", expected_version where an edit)
InstallScopeItem, ReturnScopeItem, VerifyScopeItem   # record_id, expected_version; access awp.progress.record (user)
RecordManualProgress   # iwp_id, step entries [{scope_item_id, step, done: bool}], expected_version; access awp.progress.record
StartIwpWork, CompleteIwpField   # iwp_id, expected_version, at (date, default today); access awp.iwp.edit (user)
```
Rules: a step with `scope_state:<State>` is earned when the item's state is at or beyond it (Installed counts for Planned..Installed; Verified for all); `manual` steps use the `manual_json` entries; a `record_state:<type>:<State>`
step whose type is unknown is skipped and a note says `type not recorded yet` (never an error). Void items drop out. Errors are fixed-text `AwpError` subclasses in `errors.py`.
**The four math rules (F9; S3 and S4 follow them):**
1. *Computed unfiltered, filtered on read.* The stored figure (`cur_awp_iwp_progress`, `ProgressRecorded`) is computed over every non-void item whatever the writer can see, so it never depends on who ran the command; `earned_fraction(conn, iwp_id, viewer=...)` on a read
   returns the same figure and lists only the items the viewer may open, with the note `some items not shown` when any are hidden (no count of hidden). A viewer who cannot open the IWP gets one not-found.
2. *Null est_hours.* An item with null `est_hours` weighs the mean of the non-null weights of its IWP; when all are null, every item weighs 1. The note `hours missing on n items` is written (n is of visible items).
3. *Rounding.* Sums are unrounded `Decimal` (fractions of weight and hours kept exact); a figure is rounded once, half-up, at its output (item, IWP, CWP, WBS, export cell), never at a step. Where one total is split into parts (a WBS node's earned quantity across cost-code
   allocation percentages, S3) the parts use largest-remainder allocation to 1 dp so the parts sum to the rounded total.
4. *PPC and burned (S4, S3).* PPC = IWPs committed for the week whose outcome is `done` divided by IWPs committed, as a count (not hours), 1 dp, `0.0` of zero commitments reported as null with the note `nothing committed`. Burned hours come from the cost snapshot figures of
   `cost.CostCode` read through `tl_mod_cost` for the mapped cost codes (read only); earned hours are earned pct times IWP `est_hours`; "earned vs burned" is shown only when the node has a snapshot, else `no cost snapshot`.
Each state-moving command writes the progress row in its own unit and emits `IWP.ProgressRecorded` when the figure changed. `StartIwpWork` and `CompleteIwpField` use the existing workflow moves and guard; `CompleteIwpField` writes a last `ProgressRecorded`.
**ADR-0027:** one `ProposableCommand` row each for `RecordManualProgress` and `InstallScopeItem` (tool names `propose_progress`, `propose_scope_installed`); `VerifyScopeItem`, `ReturnScopeItem`, `StartIwpWork`,
`CompleteIwpField` go to `tests/tools/proposable_exclusions.toml` with reasons (verification and field state are acts of the people on site). I4-A S2 owns that file, its test and its baseline (F5): append lines only; if the file is not on the base yet, write the lines in the report for the merge and
add nothing else.
**ADR-0025:** P2-INT is on the base; the handlers never read `intent` (say so in the report).

## Context (<= 12 files)
`packages/tl-modules/awp/src/tl_mod_awp/{module,names,commands,errors,common,guards}.py`; `handlers/scope.py`, `handlers/iwp.py` (pattern); `projectors/scope.py`;
`schema/fixtures/workflows/awp-{iwp,scope-item}.yaml`; `docs/reports/P2-I5/S1.md`; `docs/adr/0027-agent-first-layer.md` §6.
may explore: `packages/tl-modules/awp/src/tl_mod_awp/rollup.py` (S3 extends it; do not edit).

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/{progress/__init__.py,progress/engine.py,handlers/progress.py,commands.py,names.py,module.py,errors.py}`
- `packages/tl-modules/awp/tests/progress_world.py` (create, a stand-in world for S6; never reuse a real module name)
- `tests/tools/proposable_exclusions.toml` (lines appended only, if the file exists)
- pinned lists written as the union (command lists, `AGENT_MAY_NOT`, proposal count): list each in the report
- `dev/accept/P2-I5/S2.py`, `docs/reports/P2-I5/S2.md` (create)
Not allowed: schema, `tl_core/**`, other modules, `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` (registrations are supervisor glue at C2).

## Acceptance (run once each)
```
just check
uv run python dev/accept/P2-I5/S2.py
just gate packages/tl-modules/awp/tests
just gate packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_auth_review.py packages/tl-mcp tests/services/test_modules.py
```
`S2.py` (SQLite, dialect-neutral, `PASS <check>` lines, final `S2 ok`): the standard edition resolves; a project setting to an unknown edition refuses; 4 items of 10, 10 and 20 hours with the
steps 30/60/10 give the stated pct (worked example in the script, half-up at .05); a hidden item is absent on the viewer's read but counted in the stored figure (rule 1); null est_hours follows rule 2; the split of 10.0 over 33/33/34 percent gives 3.3/3.3/3.4 (rule 3); PPC of 3 done of 4 is 75.0 and of none committed is null (rule 4); `manual` entries move pct; an unknown `record_state` type adds a note and no
error; Installed twice is refused by the workflow; a stale `expected_version` is refused; `CompleteIwpField` is refused while a blocking constraint is open; `ProgressRecorded` is emitted once per change and
not on a no-op; an agent proposal of `propose_progress` is accepted only by a person holding `awp.progress.record`.

## Report requirements
Deviations first; ≤ 60 lines; the three `grep` answers; mutation: sentinel plus ≤ 5 on the rounding, the cap, the stored-unfiltered rule, the stale-version check, the guard on `CompleteIwpField`, in 3 lines.
## Escalation triggers
S1 shapes differ from this spec (stop, write the difference); the dispatcher cannot give a handler the viewer; a frozen contract change.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
