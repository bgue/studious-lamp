# P2-IP-F3 - `tl insp` and `tl checklist` writes run as the acting person

Status: ready (written r6; base `p2/ip-r3`; INSP-T04 and T05 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, access, confidentiality
Depends on: P2-INSP-T04, P2-INSP-T05 (merged); pattern P2-PTW-T04-FX (merged, `6b7b0b82`)
Branch: `p2/ip-f3-cli-viewer`
Worktree: `/home/user/wt/ip/f3` (from `p2/ip-r3`)

## Goal
`_execute` in `tl_cli/insp_write.py` and `tl_cli/checklist_write.py` builds the command, gates it and runs the handler under the process viewer, which on a dev ledger is the file owner (reads restricted records). After this ticket each runs all three under `cf.use_viewer(cf.viewer_for_actor(uow.conn(), who))`, as `tl_mod_permits/cli_permit_write.py::_execute` and `cli_isolation` do, so a refusal never names a record the acting person cannot see. Behaviour for a reader who can see the record is unchanged.

## Interfaces (change)
```python
def _execute(db: DbTarget, who: str, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    with service_errors(), open_uow(db) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), who)):
        command = build(uow)
        require_command(uow, command)
        return _handler(type(command))(uow, command)
```
Every caller passes the `who` it already computed with `acting(db, actor)` (insp_write lines 164, 213, 294; checklist_write has the same in each verb). Where a verb already opens its own `viewer = cf.viewer_for_actor(...)` inside `build`, leave that line (it is the same viewer); do not restructure. Copy the docstring of the permit `_execute`, naming the two modules.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/insp_write.py` (whole), `packages/tl-cli/src/tl_cli/checklist_write.py` (whole)
- `packages/tl-modules/permits/src/tl_mod_permits/cli_permit_write.py` (lines 55-75), `git show 6b7b0b82 -- packages/tl-cli/tests/test_cli_permit_write.py` (the spy test to copy)
- `packages/tl-cli/tests/test_cli_insp.py`, `test_cli_checklist.py` (fixtures `cli`, world helpers; names only)

## Allowed paths
- `packages/tl-cli/src/tl_cli/insp_write.py`, `packages/tl-cli/src/tl_cli/checklist_write.py` (edit)
- `packages/tl-cli/tests/test_cli_insp.py`, `packages/tl-cli/tests/test_cli_checklist.py` (add one test each)
- `docs/reports/P2-IP/IPF3.md` (create)

## Tests to add
- `test_cli_insp.py::test_an_inspection_write_runs_its_handler_as_the_acting_person` and `test_cli_checklist.py::test_a_checklist_write_runs_its_handler_as_the_acting_person`: monkeypatch the module's `_handler` with a spy that records `cf.current_viewer()` when the handler runs (copy the permit test line for line); run one verb (`plan` with the actor `user:...` the file's fixture uses; `create`); assert `seen == [expected]` with `expected = cf.viewer_for_actor(conn, actor)` read on a readonly unit of work and `expected != cf.LOWEST`. If the fixture's actor has the lowest clearance on this ledger, use the fixture user that holds a class above it and say which in the report.
- All existing tests in both files stay green unchanged.

## Acceptance
```
uv run ruff format --check packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_cli_checklist.py
uv run ruff check packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_cli_checklist.py
uv run pyright packages/tl-cli/src/tl_cli/insp_write.py packages/tl-cli/src/tl_cli/checklist_write.py packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_cli_checklist.py
just gate packages/tl-cli/tests/test_cli_insp.py packages/tl-cli/tests/test_cli_checklist.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright. Diff <= 40 lines of source.

## Escalation triggers
A verb's `build` needs a record read that must stay under the process viewer (name it); a test needs a fixture the files lack.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-IP-F3: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
