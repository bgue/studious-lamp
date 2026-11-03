# P2-I1-T11 — The increment's tests, five-reader walk and capped mutants

Status: ready when T04e, T05c, T05e, T05f, T07 are merged (C3). Written r9.
Tier: builder
Kind: piece
Review: full
Labels: tests
Depends on: S2-S6, T01-T07, T10, T10b, T10c (all merged)
Branch: `p2/i1-t11-tests`
Worktree: `/home/user/wt/i1-t11` (from `p2/i1` head)

## Goal
Every deferred test of the increment (R-P2-4: pieces and tickets were gated by acceptance scripts only) is written and RUNS green. The gate is `just gate <touched test dirs>`: tests that are only written, or skipped, do not count. A test that finds a defect in `src` is NOT fixed here: stop that item, name it under *Blocked* with the failing test's path and one-line cause, and carry on with the rest. Never xfail, skip, weaken a bound or widen the viewer to get green (AGENTS "Never").

## Allowed paths (new files unless said; no `src` file, no `schema/**`, no `dev/accept` edit)
- `packages/tl-schema/tests/test_awp_schema.py`
- `packages/tl-modules/awp/tests/` (create the directory: `conftest.py` copying the sibling `packages/tl-modules/schedule/tests/conftest.py` shape, plus the files below)
- `packages/tl-api/tests/test_api_awp.py`; append-only awp cases in `packages/tl-api/tests/test_confidentiality_walk.py` (walk at :142) and `packages/tl-mcp/tests/test_confidentiality_walk.py` (:36)
- `packages/tl-mcp/tests/test_awp_tools.py`
- `packages/tl-cli/tests/{test_cli_awp,test_awp_write,test_awp_write2,test_awp_run,test_reports}.py`
- `packages/tl-tui/tests/{test_client_awp,test_awp_text,test_text_modules_no_textual,test_cwp_register,test_wbs_screen,test_cwa_register,test_path_screen}.py` (the package log joins `test_path_screen.py`)
- `packages/tl-sim/tests/test_workface_planner.py`
- load-target and loader tests under the module's tests dir (`test_targets.py`, `test_loaders.py`, `test_fixtures.py`)
- `docs/reports/P2-I1/T11.md`

## Read first
`docs/build-spec/specs/m3-wbs-cwp.md` section 10 (test list by origin) and section 11; the reports `docs/reports/P2-I1/*.md` (each has "Guards for T11" lines with file:line, plus its decisions); STATE.md decisions D9 D10 D16 D17 D22 D26-D28 D30 D33 D37-D45 (`docs/tickets/P2-I1/STATE.md`); test patterns: `packages/tl-modules/schedule/tests`, `packages/tl-tui/tests/fakes_awp.py` (`seed_awp`), `packages/tl-tui/tests/test_tag_plain.py`, the two confidentiality walks. Seed ledger for scripts you may reuse: `dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db` (never commit `.accept`).

## Tests (the list; one test or parametrised group per bullet; both adapters where noted "2a" via the `parity` marker)
Module (`packages/tl-modules/awp/tests/`, 2a for projection, rollup and cwp):
- `test_wbs.py`, `test_path.py`, `test_cwa.py`: S3 commands and refusals; sum = 100; leaf-only map; depth bound; `expected_version`; module-only link retract. Key guard (S3F1, D9): WBS node `1` and cost code `1` coexist; a hidden record keeps the same answer as a missing one.
- `test_projection_rebuild.py` (2a): rebuild equals the incremental tables.
- `test_cwp.py`, `test_actions.py` (the access word per `RULES` row equals the command's word), `test_packages.py`: S4. Release preconditions; frozen fields after release; `not_closed`; D10: 0-line map clear (empty list clears), allocation sum with the empty list; reason code against the PathReason list; D16: `AllocateCwpToWbs` has no clear; `offline_drafts` empty for `awp.CWP`; `LinkActivity` from a CWP (S4 report).
- `test_rollup.py` (2a, property test: rebuild = incremental): S5 guards (largest remainder 33.3/33.3/33.4 and the 0.05 h tie to even; unallocated bucket; void excluded, every other state counted; 500-node bound and re-queue; D-c: a request while `running` queues exactly one new run, two requests queue one; second run with no change appends nothing; no feed card; correlation and source). Rollup totals and `by_cost_code` with packages and rollup rows.
- `test_targets.py`, `test_loaders.py`, `test_fixtures.py`: T02 guards (sum plan check; parents first; create-only through `resolve_code`; children before parents on reverse; path irreversible; D17: the second reverse of a reversed run is a no-op; admin gate); loader counts from the sample files (wbs: 12 new, 1 invalid; cwa: new 5); S6 expectation: `tl link list` on the seed shows the awp expected link (D31, no new command).
- `test_views.py`: T10, T10b, T10c. Requires-link path; view fields incl. a hidden CWP (patch `views._hidden`, D22: no awp or cost record has a class); T10F1 guard: `total_hours` never includes a hidden cost code's hours (total = visible lines + unallocated).
- Five-reader walk (S3F2, S3F3, T10F2, T10F3): for each of the five kinds of reader (`tl_core.confidentiality`, ADR-0016; copy the kinds from the two existing walks) check `cwp_detail` activities, the path lookup, WBS tree counts. T10F2 (activity refs unfiltered: `views.py:351`, schedule resolver `_LINKS_SQL`) and T10F3 need a fixture with a class; if the walk shows a leak that only a `tl_mod_schedule` change fixes, record it under *Blocked* as a finding (orchestrator decides); do not edit.
API (`packages/tl-api/tests/test_api_awp.py` + the walk): T03a eight GET routes, counts, timeline (D30: literal reading of the timeline note and a null WBS total without rollup rows are pinned as built); T03c `/awp/reports/{name}` (D33: names `x` unknown -> 404, `cwp_status`; JSON `ReportView`; CSV cells equal the JSON cells). Walk: every awp route as five readers.
MCP (`packages/tl-mcp/tests/test_awp_tools.py`): T06 four read tools and `propose_cwp` (files a pending proposal, creates nothing; a person accepts); `path_of_construction` null for no path or an unknown version (D39) and the `READING` pins; walk: hidden answers like missing.
CLI (`packages/tl-cli/tests/`): reads and groups (T04a), reports (T04b, D28: unknown wbs code exits 1; no path prints the line, exit 0; list headers print 0; difference = awp minus cost; union of codes; empty csv `""`), `test_awp_write.py` (T04c, D37: refusals: forbidden release, unknown CWP, parse, reason, `move --reason` on a reasonless action, allocate on a parent node needs a leaf), `test_awp_write2.py` (T04d: nine verbs; the three mutually exclusive option pairs exit 1 before the ledger opens; `path define` without `--step` refuses; `path define` success line on a project without a path (`defined path  version 1`); the printed version is the record version, not `current_version`; `wbs map` by exit status and version; an empty `wbs revise CODE`/`cwa revise CODE`: pin what the handler does and say which in the report, T04d open question), `test_awp_run.py` (T04e: `rollup` idempotent; `worker --once` ran=1 then ran=0; `--requeue` prints `requeued 0` first; run on a COPY of the seed, D25).
TUI (`packages/tl-tui/tests/`): `test_client_awp.py` (ApiClient, embedded and fake answer the same CWP); `test_text_modules_no_textual.py` (import each of `awp_text`, `details/awp`, `wbs_text`, `cwa_text`, `path_text`, `package_text` with `sys.modules["textual"] = None`); `test_awp_text.py` (T05a: empty Timeline heading with `No events recorded`, D38; budget and discipline in the summary and Scope; discipline label from the code list when loaded, else the code); screens `test_cwp_register`, `test_wbs_screen`, `test_cwa_register`, `test_path_screen` (+ package log) at 80 and 170 columns, plain-walk entry, keys, missing-data status. Pins from the reports: WBS cost-code cell `N · P%` (P = codes' hours over `total_hours`, `N · —` without a total); `Parent of N` counts direct children; `Leaf · Retired`; CWP register `Budget h` is left-aligned (no hook, T05d). Read widget text INSIDE the pilot (`app.screen` raises after `run_test` exits).
Sim (`packages/tl-sim/tests/test_workface_planner.py`): T07 as its acceptance (3 proposals, pending, 3 accepted, order of draws, no areas, refused area), `ACTOR_NAMES` order (assistant, workface_planner, approver), off by default, `ROLE_NAMES` and the provisioned list unchanged (D45).
Schema (`packages/tl-schema/tests/test_awp_schema.py`): S2 (the generated awp classes, pinned lists R-P2-4, the eight no-card events in `POLICY_EVENT_TYPES`, D6).

## Mutants (capped, rule 4; in your own worktree; report in 3 lines)
One sentinel mutant (proves the baseline passes and the harness kills) plus at most 5 targeted mutants from the "Guards" lists of the S3, S4, S5, T02 reports (suggested: sum = 100 `common.py:202`; Release preconditions `handlers/cwp.py:455-461`; largest remainder `rollup.py:155`; 500-node bound `worker.py:141`; D-c re-check `worker.py:172`). Mutate by editing the one `src` line in the working tree, run only the one test file that should kill it, then `git checkout -- <file>`. Never commit a mutant; `git status` clean of `src` at the end.

## Acceptance (the gate; run once at the end, and the check)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
just gate packages/tl-schema packages/tl-modules/awp packages/tl-api packages/tl-mcp packages/tl-cli packages/tl-tui packages/tl-sim 2>&1 | tee .gate/summary.txt
just gate-pg packages/tl-modules/awp 2>&1 | tee .gate/summary-pg.txt
```
Run partial paths while writing (`just gate <one dir>`), never `pytest` directly and never a suite twice for the same result. Read only `.gate/summary*.txt`, never a whole log. Any exit 3 from `gate-pg` = Postgres down: report, do not work around.

## Report requirements
`docs/reports/P2-I1/T11.md` <= 60 lines: deviations first; files and test counts per dir; the two gate summaries (last line and part lines); mutants in 3 lines; findings (`F<n> HI|MD|LO file:line`) and *Blocked* items; candidate learnings. Builder return <= 15 lines.

## Commit
Subject `P2-I1-T11: <imperative summary>` (split in several commits by directory if you like, each with the prefix); body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- *Blocked* if: a test needs a `src` change to pass (list it, continue the rest); the fixture for a hidden CWP or cost code cannot be built without a schema class; gate-pg shows figures that differ from SQLite's; the whole list cannot be finished: stop at a directory boundary, gate what exists, say which items remain.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
