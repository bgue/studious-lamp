# P2-IP-INT2 — Whole-suite failures on the integration branch after the IP merges

kind: piece
review: full
branch: p2/ip-int (work in place; worktree /home/user/wt/ip-int; head ffc27ea3)
Labels: merge, test pins, confidentiality (walks), offline capture.

## Why
The per-directory whole-suite run on p2/ip-int (before ffc27ea3) failed in four directories. Full logs (read the FAILED
lines and their tracebacks; do not re-run a whole directory to find them):
- packages/tl-cli/tests: `.gate/each-2.log` (12 F). test_cli_gastest x6 are fixed by ffc27ea3 (merged 6f7a8e0c); others:
  test_cli_config ls, test_cli_controller_gates::test_every_controlling_cli_path_is_gated, and the rest in the log.
- packages/tl-core/tests: `.gate/each-3.log` (2 F, test_offline_capture: decision table and record-type rows vs modules).
- packages/tl-mcp/tests: `.gate/each-6.log` (6 F: test_confidentiality_walk x2, test_mcp_get_settings, test_mcp_write_tools
  human-gate message, test_module_conformance_walk x2).
- packages/tl-tui/tests: `.gate/each-8.log` (10 F: settings lists, module_roles_log snapshots, remote_settings).
Likely causes: exact pins (settings list, controller paths, offline record types, module role list) that do not yet know the
rows the IP modules (forms, qr, permits, quality inspections) add; MCP walkers missing argument values (as twin_channels was).

## Goal
1. Root-cause each failure. Where a pin is an exact list built from installed modules, add the new rows (union; never delete a
   row that still exists). Snapshots: regenerate with the repo's own update flag only after reading the diff (new module rows,
   nothing else changed); say in the report what changed in each snapshot.
2. Controller gates: every new controlling CLI path must be gated; if one is ungated in code, that is a real bug: fix it in code
   (gate it with the module word, as the neighbouring paths do) and say so. Never mark a controlling path exempt to get green.
3. Offline capture: the decision for each new type/command must follow the rule the test states; if a module declares the wrong
   offline class, fix the declaration, not the test. Any change to a module's declared offline class or to a schema file needs
   an APPROVALS line: say so in the report (the orchestrator writes it).
4. Walk tests: add argument values only (as `tests/confidentiality/twin_channels.py` does for list_gas_tests); never weaken an
   assertion. Hidden must look exactly like missing.
5. Behaviour unchanged except for real bugs you name.

## Gates (one call at a time; never `just check` or whole-repo pyright; at most one pytest at a time)
ruff check + format, `uv run pyright <changed .py>`, generate/openapi --check; `just gate <each failing test file>` (list them all
in one call per directory); then `just gate packages/tl-mcp/tests/test_mcp_server.py packages/tl-api/tests/test_auth_review.py`.
Save summaries in `.gate/int2-summary.txt`. Do not delete `.gate/each-*.log`.

## Report
Append a section `## INT2` to `docs/reports/P2-IP/INT1.md` (at most 30 lines), no model names. Commit trailers exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4
