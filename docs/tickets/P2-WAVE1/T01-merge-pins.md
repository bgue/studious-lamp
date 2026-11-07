# P2-WAVE1-T01 — Fix the tests the wave 1 merge broke (pins, two small defects, one scenario gap)

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tests
Branch: `p2/wave1-close-t01-merge-pins`   (from p2/wave1-close)

## Goal
`p2/wave1-close` merges M3 (p2/i1), M4 (p2/i3) and the web client (p2/web1). Each stream's tests passed alone; together,
the failures below remain. Most are **pins**: a count, list or set that each stream extended for its own module,
which now must hold the union of both. Fix each as its group says. No change under `packages/*/src` except item B1.
Run each failing test, read its assertion, make the smallest fix, re-run it.

## A. Pins: update the pinned value to the union of both streams (awp and materials both present)
1. `packages/tl-api/tests/test_api_document_controller.py::test_the_controlling_set_is_the_twelve_and_the_actions_follow` (awp count is 14 with `ReinstateWbsNode`).
2. `packages/tl-api/tests/test_api_proposals.py::test_an_agent_token_cannot_run_any_record_changing_command` (the sum of the per-module counts must equal the commands minus the message commands).
3. `packages/tl-api/tests/test_commands.py::test_every_command_in_the_table_has_a_route` (total 207: fix the sum of per-module counts).
4. `packages/tl-api/tests/test_commands.py::test_the_controller_actions_are_exactly_the_commands_marked_controller` (union of both modules' controller actions).
5. `packages/tl-cli/tests/test_cli_controller_gates.py::test_every_controlling_cli_path_is_gated`.
6. `packages/tl-mcp/tests/test_mcp_server.py::test_the_phase_0_surface_is_read_tools_proposing_tools_and_post_feed` (add the ten materials tools beside the awp ones).
7. `packages/tl-mcp/tests/test_mcp_write_tools.py::test_write_mode_is_refused_with_the_human_gate_message` (add `propose_reservation`).
8. `packages/tl-sim/tests/test_workface_planner.py::test_the_actor_order_is_assistant_planner_approver_and_off_by_default` (the actual order includes `workface_planner` and the materials coordinator; pin the actual registry order and keep the "off by default" check).
9. `packages/tl-schema/tests/test_ddl_views.py::test_every_record_class_of_the_committed_modules_has_a_view` (add the `v_materials_*` views in sorted order).
10. `packages/tl-tui/tests/test_module_roles_log.py` 80x24 and 170x40 snapshots: nine modules now. Regenerate with `--snapshot-update` for these two tests only, then confirm the visible change is only the module rows and count.
11. `packages/tl-tui/tests/test_plain_walk.py::test_admin_ctrl_d_walk_shows_technical_text_then_hides_it`: read the assertion; if a pinned list or text lacks the other module's entry, union it; if it is anything else, stop and write Blocked with the assertion.

## B. Two small real defects (from M4)
1. `packages/tl-schema/tests/test_catalog.py::test_samples_validate_against_their_own_schemas`: the sample of `MTOLine.Assigned` carries the 27-character id `01J9Z6Q4W3X2Y1V0T9S8R7Q6P11`. Find it in `schema/modules/materials/` (the event's example), make it a valid 26-character ULID (drop the last character), then `just gen` to regenerate the catalog. This is the one allowed change outside tests.
2. `packages/tl-schema/tests/test_type_labels.py::test_labels_are_plain_words`: the label `Material take-off` fails the regex `[A-Z][A-Za-z]*( [A-Za-z]+)*`. A hyphenated word is a plain word: change the test's pattern to allow a hyphen inside a word (`[A-Z][A-Za-z]*(?:-[A-Za-z]+)*( [A-Za-z]+(?:-[A-Za-z]+)*)*`). Do not change the label.

## C. One scenario gap (pre-existing on M3)
`tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog`: the scenario
`tests/webhooks/scenario.py` has a table of record types with their created and extra events (M4 added its rows under
the comment `# materials (P2-I3)`); M3 never added the awp rows, so the awp event types are never delivered. Add awp rows
in the same shape for every awp event type the catalog lists (`grep "awp" ` the catalog index or read
`schema/modules/awp/events.yaml`), so the thin subscription sees each one. If an awp event cannot be produced by the
table's generic mechanism, stop and write Blocked naming it.

## Allowed paths
- the test files named above, `tests/webhooks/scenario.py`
- `schema/modules/materials/**` (only the B1 example id) and the files `just gen` regenerates
- `docs/reports/P2-WAVE1/T01.md` (create)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate <each test file named above>` (one run listing the files) ends `gate: PASS`
