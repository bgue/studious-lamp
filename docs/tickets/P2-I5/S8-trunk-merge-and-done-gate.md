# P2-I5-S8 — Merge the trunk (P2-I4A done) and close the DONE-gate registries

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: integration, merge, tests, webhooks, confidentiality, settings
Branch: `p2/i5-s8-done`
Worktree: harness-created under `/home/user/wt/i5/s8` (from `p2/i5` head)

## Goal
`p2/i5` carries the trunk (`claude/wizardly-allen-m2v96s`, P2-I4A requisitions merged) and the registry tests the
whole suite pins are green. Two steps, each its own commit. The model is P2-PUNCH-S3 (same job on the punch branch,
report `docs/reports/P2-PUNCH/S3.md` on branch `p2/punch-s3-done`, `git -C /home/user/wt/punch/s3 log`) and
P2-I4A-S5 (`docs/reports/P2-I4A/S5.md` on the trunk).

1. **Merge the trunk** (`git merge --no-ff claude/wizardly-allen-m2v96s`, never rebase). 27 files conflict, almost all
   lists where requisitions and awp each added rows: keep both sides (union, in the file's own order). Rules:
   - `tests/tools/proposable_exclusions.toml` comes from the trunk (requisitions); add a row or exclusion for every
     awp command that has none (SR3 F4), so the row-or-exclusion check covers awp.
   - Settings (`tl_core` settings tests, `tests/settings/test_phase2_keys.py`, tl-api, tl-cli, tl-mcp, tl-tui
     settings tests and the settings snapshot): union of both sides' keys; keep D31 (user layer takes `ui.*` and
     `tui.*`) and requisitions' `requisitions.forecast.weeks`.
   - `tests/webhooks/scenario.py` MODULE_STREAMS: both modules' streams.
   - `packages/tl-schema/src/tl_schema/generated/**`: take either side, then regenerate with the repo's codegen
     (`just gen` or `uv run python -m tl_schema.generate`); never hand-edit. `uv.lock` if it conflicts: `uv lock`.
     `docs/reference/openapi.json` if touched: regenerate.
   - TUI snapshots (`test_command_palette.raw`, `test_the_settings_list_snapshot.raw`): take either side, then
     regenerate with the snapshot-update flag after the code merges, reading each text diff (only rows of the two
     modules and scrollbar glyphs may change).
   - Pinned counts (`test_access_words.py`, `test_offline_classes.py`, others): both modules' additions, recomputed.
2. **Close the registry failures.** Run the registry files below once after the merge (one pytest session):
   `packages/tl-api/tests/{test_auth_review,test_error_table,test_api_module_roles,test_api_settings,test_client_settings,test_confidentiality_walk}.py`,
   `packages/tl-cli/tests/{test_cli_controller_gates,test_cli_config}.py`, `packages/tl-core/tests/test_offline_capture.py`,
   `packages/tl-core/tests/auth/test_access_words.py`, `packages/tl-mcp/tests/{test_confidentiality_walk,test_mcp_server,test_mcp_write_tools,test_mcp_get_settings}.py`,
   `packages/tl-tui/tests/{test_module_roles_log,test_snapshots_links,test_snapshots_settings,test_embedded_settings,test_fakes_settings,test_remote_settings,test_settings_screen}.py`,
   `packages/tl-modules/awp/tests`, `packages/tl-modules/requisitions/tests`, `tests/confidentiality`, `tests/contract`,
   `tests/parity/test_webhooks_parity.py`, `tests/services`, `tests/settings`, `tests/webhooks`, `tests/tools`.
   Fix each failure at its root (the S5 and S3 reports list the usual roots), never by skipping, deselecting or
   weakening a test.

## Allowed paths
- Every file the trunk merge touches (to resolve it), `tests/**`, `packages/*/tests/**`
- `packages/tl-api/src/tl_api/errors.py`, `packages/tl-api/src/tl_api/auth*.py` (agent decisions table only),
  awp CLI files under `packages/tl-cli/src/tl_cli/` (gates only), generated files via codegen
- `docs/reports/P2-I5/S8.md`
- Not `schema/` beyond conflict resolution; not module source beyond conflict resolution. A needed source change
  outside these goes under Blocked.

## Acceptance
```
uv sync --all-packages --all-extras
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest -q -p no:cacheprovider --basetemp=/tmp/pt-i5-s8 <the registry files above>
```
One pytest session at a time; never two directories as large as tl-api and tl-tui in one session (split them).
Do NOT run `just gate` or the whole suite: the orchestrator runs it split.

## Report requirements
Builder return <= 15 lines; report <= 60 lines: conflicts resolved (grouped), then one line per failure with root
cause and fix. Commit subjects `P2-I5-S8: ...`; the commit body ends with the trailer lines
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(builder writes here)

## Decision
(orchestrator writes here)
