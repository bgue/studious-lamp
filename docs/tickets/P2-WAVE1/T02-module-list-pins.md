# P2-WAVE1-T02 — Module-list pins and a test stand-in that now collides with the real awp module

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tests
Branch: `p2/wave1-close-t02-module-pins`   (from p2/wave1-close)

## Goal
After the wave 1 merge nine modules are installed (awp and materials both). Fix these failing tests; change tests only.
1. `tests/services/test_module_role_seams.py`: three tests build a stand-in module spec named `awp` with commands
   `ReleaseCwp` / `ViewCwp` (lines about 100-120). The real awp module is now installed, so `command_index()` raises
   "command 'ReleaseCwp' is declared by modules 'awp' and 'awp'". Rename the stand-in to a name no real module uses
   (`example`) with commands no module declares (`ReleaseThing`, `ViewThing`) and words `example.thing.release`,
   `example.view` (or the misspelt one the refusal test needs), and update the assertions to the new names. Keep what
   each test proves.
2. The same file, `test_every_module_row_of_the_api_table_is_in_the_index_and_nothing_else_is` (line about 91) and
   `test_every_module_with_a_record_type_is_walked_by_the_require_generic_test` (about 424): pinned module sets/lists ->
   the nine installed modules (sorted as the code returns them).
3. `tests/services/test_modules.py::test_the_installed_modules_are_found_through_their_entry_points` (about 145): the
   nine modules.
4. `tests/services/test_modules_offline.py` (about 111 and 132): count 9, not 8.
5. `tests/parity/test_webhooks_parity.py::test_every_catalog_event_type_is_delivered_and_valid[sqlite]`: same cause as
   T01 item C (the scenario lacks awp rows). Do not edit the scenario here: T01 adds the awp rows. Just confirm, after
   merging the T01 branch into yours if it is already merged into p2/wave1-close, that this test passes; if T01 is not
   merged yet, say so in the report and leave the test as it is.

## Allowed paths
- `tests/services/test_module_role_seams.py`, `tests/services/test_modules.py`, `tests/services/test_modules_offline.py`
- `docs/reports/P2-WAVE1/T02.md` (create)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/services | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
