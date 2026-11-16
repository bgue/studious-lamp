# Report - P2-PTW-T04 (harness id P2-IP-PTWT04), second attempt

Branch: `p2/ptw-t04-cli-permit-writes`   Commit(s): see the branch log (review fix is a new commit on top of `ed39236d`)

## Deviations
- Report path is the harness path `docs/reports/P2-IP/PTWT04.md`, not the ticket's `docs/reports/P2-PTW/T04.md`. Same as the PTWT01 report.
- Review fix (F1, med): added `test_a_for_key_the_actor_cannot_see_prints_the_same_text_as_an_unknown_key`. A hidden `--for` key and an unknown `--for` key must print the same text. No other code or test changed.
- Ticket test 4 also has a hidden-permit case for the nine state verbs. That was already covered by `test_a_restricted_permit_answers_as_missing_to_a_reader_who_cannot_see_it`.

## Changed files
- `packages/tl-cli/tests/test_cli_permit_write.py` - one new test for a hidden `--for` key against an unknown `--for` key.
- `docs/reports/P2-IP/PTWT04.md` - this report.

Module source (`cli_permit_write.py`) is unchanged in this attempt.

## Commands and output
Mutation check (temporary, then reverted with `git checkout`): `_for_id` changed from `cf.use_viewer(viewer)` to `cf.system_view()`.
```
$ uv run pytest packages/tl-cli/tests/test_cli_permit_write.py -q -k cannot_see
FAILED packages/tl-cli/tests/test_cli_permit_write.py::test_a_for_key_the_actor_cannot_see_prints_the_same_text_as_an_unknown_key
1 failed, 1 passed
```
Unmutated, the new test and the unknown-`--for` test pass:
```
$ uv run pytest packages/tl-cli/tests/test_cli_permit_write.py -q -k "cannot_see or unknown_for"
3 passed
```
Acceptance:
```
$ uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
37 files already formatted
$ uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
All checks passed!
$ uv run pyright packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-cli/tests/test_cli_permit_write.py packages/tl-modules/permits/tests/test_module_spec.py
part 1: exit 0, 21 passed in 31.52s
gate: PASS
```
The first `ruff format --check` run failed on the new assertion line (over 100 columns). I ran `ruff format` on the test file and reran all four commands; the output above is from the rerun.

## Tests added
- `packages/tl-cli/tests/test_cli_permit_write.py::test_a_for_key_the_actor_cannot_see_prints_the_same_text_as_an_unknown_key` - `rob` requests with `--for` set to the key of a restricted correspondence item. Output is `error: no record <KEY>`, identical to the unknown-key output apart from the key typed. Fails if `_for_id` stops resolving under the actor's viewer.

## Learnings (proposed)
- `permit_world.World.hidden_record()` returns an id only. A test that needs the hidden record's key has to read `cur_core_record.key` by id, as the existing restricted-permit test does.

## Open questions / Blocked
none
