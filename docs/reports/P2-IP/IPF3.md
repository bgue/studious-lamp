# Report — P2-IP-F3

Branch: `p2/ip-f3-cli-viewer`   Commit(s): see `git log -1` on the branch (the implementation commit and this report commit)

## Deviations
none in scope. Worktree is `/home/user/wt/ip4/ipf3` (from the dispatch, not the ticket's `/home/user/wt/ip/f3`), based on `229bc67b`; the dispatch names this branch, which supersedes the ticket's `Branch` field.

## Changed files
- `packages/tl-cli/src/tl_cli/insp_write.py` — `_execute(db, who, build)` runs build, gate and handler under `cf.use_viewer(cf.viewer_for_actor(uow.conn(), who))`; `plan`, `record`, `_run` pass `who`.
- `packages/tl-cli/src/tl_cli/checklist_write.py` — same change; `create`, `edit`, `_run` pass `who`.
- `packages/tl-cli/tests/test_cli_insp.py` — adds `test_an_inspection_write_runs_its_handler_as_the_acting_person`; imports `Any`, `insp_write`.
- `packages/tl-cli/tests/test_cli_checklist.py` — adds `test_a_checklist_write_runs_its_handler_as_the_acting_person`; imports `Any`, `checklist_write`, `cf`.
- `docs/reports/P2-IP/IPF3.md` — this report.

Source diff: 36 changed lines across the two source files (under the 40 limit).

## Commands and output
```
$ uv run ruff format --check <4 files>
4 files already formatted
$ uv run ruff check <4 files>
All checks passed!
$ uv run pyright <4 files>
0 errors, 0 warnings, 0 informations
$ uv run pytest test_cli_insp.py test_cli_checklist.py -q -k acting_person
2 passed, 23 deselected in 12.29s
$ just gate packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_cli_checklist.py
part 1: exit 0, 25 passed in 62.05s (0:01:02)
gate: PASS
```

## Tests added
- `test_cli_insp.py::test_an_inspection_write_runs_its_handler_as_the_acting_person` — spies `insp_write._handler`; `plan` as `user:uma` records `cf.current_viewer()` equal to `viewer_for_actor(conn, "user:uma")`, and that viewer is not `cf.LOWEST`.
- `test_cli_checklist.py::test_a_checklist_write_runs_its_handler_as_the_acting_person` — same spy on `checklist_write._handler`; `create` as `user:uma`.

The fixture actor `uma` holds a class above LOWEST on this ledger (the assertion `expected != cf.LOWEST` passes), so the ticket's fallback was not needed. All existing tests in both files pass unchanged.

## Learnings (proposed)
- The `Read` tool must be used on a file before `Edit` even when its contents were already shown by `cat` in Bash; the first batch of edits failed for that reason.
- The ticket's Context line for `cli_permit_write.py` says lines 55-75; the permit `_execute` is at lines 63-73 (the rest is `_handler` and `_model`).

## Open questions / Blocked
none
