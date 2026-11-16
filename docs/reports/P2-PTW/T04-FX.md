# Report — P2-PTW-T04-FX
Branch `p2/ptw-t04-fx-viewer`. Commit: `P2-PTW-T04-FX: permit writes run as the acting person`.

## Deviations
Commit trailer is the harness-required attribution line, not the model line the ticket gives.

## Changed
- `cli_permit_write.py`: `_execute(db, who, build)` runs build, gate and handler under `viewer_for_actor(who)`; `request` and `_run` pass `who`.
- `test_cli_permit_write.py`: one test added. No T04 refusal names a record (blockers are codes; lookups use `load_record`), so it spies on the viewer.

## Tests added
- `test_a_permit_write_runs_its_handler_as_the_acting_person`: the handler sees `viewer_for_actor(user:rob)`, not `LOWEST`.

## Commands and output
```
$ ruff check (2 files)        All checks passed!
$ ruff format --check         2 files already formatted
$ uv run pyright (2 files)    0 errors, 0 warnings, 0 informations
$ just gate <permit_write> <isolation>
part 1: exit 0, 25 passed in 59.37s
gate: PASS
```

## Learnings / open questions: none
