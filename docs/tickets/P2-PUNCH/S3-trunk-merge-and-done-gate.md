# P2-PUNCH-S3 — Merge the trunk (P2-I4A done) and close the DONE-gate failures

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: integration, merge, tests, webhooks, confidentiality
Branch: `p2/punch-s3-done`
Worktree: harness-created under `/home/user/wt/punch/s3` (from `p2/punch` head)

## Goal
`p2/punch` carries the trunk (`claude/wizardly-allen-m2v96s` @17f86bf0, P2-I4A requisitions merged) and the whole
suite is green. Two steps, in this order, each its own commit:

1. **Merge the trunk** (`git merge --no-ff claude/wizardly-allen-m2v96s`, never rebase). 25 files conflict, almost all
   lists where requisitions and punch each added rows: keep both sides (union, in the file's own order). Rules:
   - `packages/tl-core/src/tl_core/confidentiality.py`: `SUBJECT_LINKS` is the union of both modules' rows (D15);
     keep requisitions' two-hop `_HOPS` logic; no row dropped or changed.
   - `tests/tools/proposable_exclusions.toml` (add/add): union of both lists. Then
     `packages/tl-modules/requisitions/tests/test_actions_and_words.py:34` must compare only requisitions' own
     commands (SR3 F4), not the whole file.
   - Generated files (`packages/tl-schema/src/tl_schema/generated/**`): take either side, then regenerate with the
     repo's codegen (`just gen` or `uv run python -m tl_schema.generate`); never hand-edit. `uv.lock`: take either
     side, then `uv lock`. `docs/reference/openapi.json` if touched: regenerate.
   - Pinned counts in tests (`test_ddl*.py`, `test_generate.py`, `test_offline_classes.py`, `test_access_words.py`,
     `tests/services/test_modules.py`): both modules' additions, recomputed, not one side's number.
2. **Close the DONE-gate failures.** The punch branch's own whole-suite run (2026-11-12, logs in
   `/home/user/wt/p2-punch/.gate/{dbg.log,rest.txt,rest2.txt}`) failed 20 tests, all registries the `quality` punch
   module must join. P2-I4A-S5 fixed the same set for requisitions: read `docs/reports/P2-I4A/S5.md` and its commit on
   the trunk for the pattern of each. Fix at the root, never by skipping, deselecting or weakening a test:
   - `packages/tl-api/tests/test_auth_review.py` (2): decide every new punch route action for agents.
   - `packages/tl-api/tests/test_error_table.py`: a row per punch service error, mirroring the other modules
     (scope 422, rule 422, state 409, stale 409); a not-found must read like hidden.
   - `packages/tl-cli/tests/test_cli_controller_gates.py`: gate the punch CLI paths that need a controller word.
   - `packages/tl-core/tests/test_offline_capture.py` (2): the oracle's pinned drafts for the punch kinds, matching
     the module declaration (check the spec first; a mismatch goes under Blocked).
   - `tests/confidentiality/test_twin_walk.py` (4): argument values for the punch tools in `twin_channels.py`.
   - `tests/contract/test_webhook_catalog_contract.py`, `tests/parity/test_webhooks_parity.py[sqlite]`: the punch
     streams in `tests/webhooks/scenario.py` MODULE_STREAMS (opener + followers in a valid order).
   - `tests/services/test_module_role_seams.py` (2), `tests/services/test_modules_offline.py` (2): the module in
     the tables and counts. Also add to `packages/tl-api/tests/test_api_module_roles.py` the explicit assert the
     seams test has (S5 review nit: a module excluded from the API-table check must assert it has no COMMANDS rows).
   - `packages/tl-tui/tests/test_module_roles_log.py` (2), `test_snapshots_links.py::test_command_palette`:
     regenerate the snapshots with the repo's snapshot-update flag only after reading each text diff: only
     punch/requisitions rows and scrollbar shifts may change; anything else goes under Blocked.
   - `tests/webhooks/test_dispatcher.py` replay: fixed by the trunk merge (tour clock restore, S5 item 6); confirm.
   After the merge, rerun these files: new failures caused by the two modules meeting go in the same commit.

## Context (read these, nothing else up front)
- `docs/reports/P2-I4A/S5.md`; `git show --stat` of the S5 merge on the trunk (`git log --oneline --grep 'merge S5'`)
- The failing test files above; `docs/tickets/P2-PUNCH/STATE.md` (D14-D30)

## Allowed paths
- Every file the trunk merge touches (to resolve it), `tests/**`, `packages/*/tests/**`
- `packages/tl-api/src/tl_api/errors.py`, `packages/tl-api/src/tl_api/auth*.py` (agent decisions table only),
  the punch CLI files under `packages/tl-cli/src/tl_cli/` (gates only), generated files via codegen
- `docs/reports/P2-PUNCH/S3.md`
- Not `schema/` beyond conflict resolution; not module source beyond conflict resolution. A needed source change
  outside these goes under Blocked.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest -q -p no:cacheprovider --basetemp=/tmp/pt-punch-s3 <the failing files above>
```
One pytest session at a time (the box is shared). Do NOT run `just gate` or the whole suite: the orchestrator runs
it split. Mutation: none (registries).

## Report requirements
Builder return <= 15 lines; report <= 60 lines: the conflict files resolved (one line each, or grouped), then one
line per failure with root cause and fix. Commit subjects `P2-PUNCH-S3: ...`; the commit body ends with the trailer
lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(builder writes here)

## Decision
(orchestrator writes here)
