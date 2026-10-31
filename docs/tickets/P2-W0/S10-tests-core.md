# P2-W0-S10 (TB) — Tests for the readiness contract, reserved names, 11 keys, targets, offline classes and the relay tools

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: tests, core, schema
Depends on: W0-B1, W0-B2, OC-S1, OC-S2, T04 (OC-T1), T05 (OC-T2), T06 (OC-T3), T08 (OC-T4), A1 to A3 (all merged on `p2/w0`)
Branch: `p2/w0-s10-tests-core`

## Goal
Every test file the offline, readiness, reserved-name, settings-key, target and tool specs named exists and passes, the old-text pins
that merged work broke are updated, and the settings snapshot (Q4) is reviewed and regenerated. This piece writes tests only; it never
edits `src`, `schema/**` or `dev/accept/**`. A test that shows a defect in source is reported under *Blocked* with the test id (no source
fix, no skip, no xfail; AGENTS.md "Never").

Do not discuss the commit trailer in the report; no model names anywhere in committed files.

## Owner policy (read first)
Tests run **once**, at the end, by the orchestrator over the whole suite. You write them and run **only your own new or changed files**,
one part at a time: `just gate <file> [<file>...]` (one pytest session, log in `.gate/`), summary saved with `| tee .gate/summary.txt`.
Never `just test`, a directory-level or whole-suite gate, or `gate-pg`. Run `just check` once at the end. Never delete
`/tmp/pytest-of-root`, never `pkill`. One extra run is allowed for each *existing, unchanged* file named under "Run once".

## Brief references
- `docs/build-spec/specs/offline-classes.md` §4 (the class table), §5 (the rule), §7 rows S1, S2, T1 to T3 and the mutation guards;
  `docs/build-spec/specs/wave0.md` §3, §4, §5; `docs/build-spec/phase2-contracts-draft.md` §1, §7 (frozen).
- Reports (guard sites, behaviour, pins): `docs/reports/P2-W0/{W0-B1,W0-B2,OC-S1,OC-S2,OC-T3,OC-T4,T04,T05,A1,A2,A3}.md`.
- Oracles: `dev/accept/P2-W0/{W0-B1,W0-B2,OC-S1,OC-S2,OC-T1,OC-T2}.py` compute expectations independently (OC-S2 has an apart-written
  decision table: 2604 rows); reuse the approach, not the code.

## Test files to write (verified paths; none exists unless marked)
1. **OC-S1 and T08:** `packages/tl-schema/tests/test_offline_classes.py`: every `TYPE_LABELS` type has a class and nothing else; the
   spec §4 table pinned cell for cell; missing, unknown, multi-type and stream-without-class values raise `OfflineClassError`; output
   deterministic; `OFFLINE_STREAMS` holds the spec streams **and `core.InboundDelivery: none`** (T08).
2. **OC-S2:** `packages/tl-core/tests/test_offline_capture.py` (every branch of `capture_allowed`; authority always allowed; node kinds;
   `stream_class` unknown = `none`; `node_kind()` values and its error text; `require_node_built`), `tests/services/test_modules_offline.py`
   (three load errors: undeclared type, drafting entry on a `full` type, `controller` command listed; plus the two extra messages in
   `OC-S2.md` Deviation 2), `tests/extypes/test_extype_offline.py` (existing dir; `tl:offline` read from an extension `type.yaml`,
   default `none`, bad value a compile `TypeIssue`, not in `schema_hash`), and the start-up refusal in
   `packages/tl-api/tests/test_api_node_kind.py` (503 `node_kind_not_built` row; `TL_NODE_KIND=device` refuses before any ledger opens).
3. **T04 (OC-T1):** `packages/tl-api/tests/test_api_record_types.py` (rows equal `record_type_rows()`, `engineering.Tag` is `full`, five
   fields per row, 401 unauthenticated, an agent token allowed by `reference.read`), `packages/tl-tui/tests/test_client_record_types.py`
   (embedded client and the fake). Run once: `packages/tl-api/tests/test_confidentiality_walk.py` (the route has no path parameter and is walked automatically).
4. **T05 (OC-T2):** `packages/tl-tui/tests/test_details_offline_row.py` (technical mode shows `Offline class` with the three wordings;
   plain mode shows no row and makes no `record_types` read; a client whose `record_types` raises leaves the rows unchanged; the plain walk
   shows no offline word). `DisplayMode()` takes no arguments: set `.technical` on an instance.
5. **T06 (OC-T3):** `packages/tl-cli/tests/test_new_record_type_offline.py` (`tl new record-type` writes `tl:offline: none` and the TODO
   comment line). Run once: `packages/tl-cli/tests/test_cli_new_record_type.py` (byte compare against the updated expected file).
6. **W0-B1:** `tests/contract/test_readiness_contract.py` (exists, written by W0-B1, never run: run it, fix the test only), 
   `tests/contract/test_reserved_prefixes.py` (`ready:`, `rollup:`, `progress:` correlation and `job:` source refused at the body-model
   check and through the API walk; the 422 shape), `tests/settings/test_phase2_keys.py` (the 11 keys: type, default, bounds, scopes,
   `lockable`; platform file defines 28 keys), `packages/tl-core/tests/test_readiness_registry.py` (`load_checks`: empty by default;
   duplicate name, load failure, non-check, bad name, over `MAX_CHECKS` raise `ReadinessLoadError`, message keeps the exception type only).
   Add to `tests/extypes/test_names_and_lock.py` a case that `awp`, `materials`, `scaffold` namespaces are `LayoutError` (reserved).
   Run once: `packages/tl-api/tests/test_api_workflow_roles.py` (R-P2-3 stays closed).
7. **W0-B2:** `packages/tl-modules/legacy/tests/test_load_targets.py` (registry, duplicate name = `ModuleLoadError`, unknown target, scope
   project and company, mapping form), `packages/tl-modules/documents/tests/test_publish_targets.py` (duplicate, unknown =
   `PublishRefusedError`, `tags` and `documents` built-ins behave as before), `packages/tl-cli/tests/test_cli_load_targets.py` (`tl load
   targets` prints `documents legacy project` and `tags legacy project`; `open --company` with a project target refused; exactly one of
   `--project` and `--company`).
8. **A1 to A3:** `tests/tools/test_state.py`, `test_review_pack.py`, `test_relay_lint.py` exist (written by the tickets, never run). Run
   them; fix the tests; if a tool disagrees with Appendix A of the skill `subagent-throughput-process` or with the decisions
   D9 (A1 base `main`, 40 lines; A2 60 lines, problem lines never hidden), write the finding under *Blocked* (tools are not yours to edit).

## Old-text pins to fix (by reading the report, then running the file)
| Where | Old text | Source |
|---|---|---|
| `packages/tl-tui/tests/test_details_registry.py:43` | technical label list `["Key","Version","Scope","Schema hash"]` for `documents.Document` gains `Offline class` (position: read `details_for`) | T05 report |
| `packages/tl-tui/tests/test_snapshots_settings.py::test_the_settings_list_snapshot` | 11 new keys change the list (Q4) | W0-B1 report |
| `packages/tl-schema/tests/` count or name pins of `OFFLINE_STREAMS`, `generated/docs/offline-classes.md` row count | `core.InboundDelivery` added (T08); none found by the T08 report, grep to confirm | T08 report |
| `packages/tl-cli/tests/expected/record_type/weld_inspection.yaml` | already updated by T06; leave as is | T06 report |

## Snapshots (Q4; list each in the report)
Review `test_the_settings_list_snapshot` first: run it, read the SVG diff, and regenerate with `uv run pytest <node id> --snapshot-update`
**only if** the diff is exactly the 11 new keys appearing in the list (name order as the screen sorts them). Any other snapshot that
differs and is not explained by a merged ticket (T05 expects none) is not regenerated; list it under *Blocked*.

## Mutants (sentinel + at most 5, own worktree, each killed by your own new file; restore after each; 3-line report)
Sentinel: `capture_allowed` always returns allowed. Then (`tl_core/offline.py`, line numbers in `OC-S2.md`): `central_act` check after the
class check; `authority` short-circuit removed; unknown type allowed; `draft_only` without listing allowed; duplicate load-target name accepted
(`targets.py load_targets`). If budget remains: unknown publish target falls back to `tags`; `job:` prefix dropped from `reserved.py`.

## Context (read these; the rest by `grep`)
The reports above, `docs/build-spec/specs/offline-classes.md` §4/§5, `packages/tl-core/src/tl_core/offline.py`,
`packages/tl-schema/src/tl_schema/generated/offline_classes.py`, `tests/auth/authworld.py` (fixture pattern), `dev/accept/P2-W0/OC-S2.py`.

## Allowed paths
Create or change only the test files named above; `tests/tools/*` (the three); `packages/tl-tui/tests/__snapshots__/test_snapshots_settings/**`;
`docs/reports/P2-W0/S10.md` (create). Everything else read-only (`src/**`, `schema/**`, `dev/**`, `docs/reference/**`).
(TA's piece owns `packages/tl-core/tests/auth/`, the roles tests and the admin snapshots: do not touch them.)

## Acceptance
```
just check
just gate <each new or changed test file>      # once per group; all PASS
```
Expected: every new file passes. Report counts per group and the 3-line mutation result.

## Report requirements (<= 60 lines; deviations first)
Files written (path, test count); pins fixed (old to new); snapshot reviewed (diff described) and regenerated or not; run-once files and
results; defects found (test id, *Blocked*); mutation lines; commands with <= 5 decisive output lines each.

## Escalation triggers
- A test shows a source or tool defect, or a pin cannot be fixed without touching source.
- The settings snapshot differs by more than the 11 keys.
- A test needs a network or a Postgres server (write it, mark `requires_postgres`, do not run).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
