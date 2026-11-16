# P2-PTW-T11 - Terminal: `permit_text.py`, the permit register and record screen, palette glue

Status: staged (r6; dispatch after PTW-T10 merges; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, safety
Depends on: P2-PTW-T10 (client methods, fake, `permit_command`)
Branch: `p2/ptw-t11-terminal`
Worktree: `/home/user/wt/ptw/t11` (from `p2/ip-r3`)

## Goal
`tl_tui/permit_text.py` (Textual-free), `PermitLogScreen(client, project)` and `PermitScreen(client, project, key)` in `tl_tui/widgets/permit_log.py`, reachable from the palette by id `permits`. No business logic: the screens call `list_permits`, `get_permit`, `list_gas_tests` and, for the actions below, `permit_command`. Same shape and method as `docs/tickets/P2-INSP/T10-terminal.md` (read it and its report `docs/reports/P2-IP/INSPT10.md`; copy its structure, not its names). Load the `tui-layout` skill. A safety screen: a state that is not valid for work (Lapsed, Suspended) reads as a stop, in words, not colour alone (`tui-layout` rules).

## Interfaces (create; names exact)
```python
# permit_text.py
PERMIT_COLUMNS = ("Number", "Subject", "State", "Type", "Area", "Holder", "Valid until", "For")
PERMIT_DROP = ("For", "Holder", "Area"); PERMIT_RIGHT = ()
def permit_cells(row, labels=None) -> tuple[str, ...]       # Valid until `YYYY-MM-DD HH:MM UTC` or "-" ; Type readable (`Hot work`); Holder via actor_label when it is an actor, else as stored
def permit_summary(rows, total, shown, *, state=None, permit_type=None) -> str   # `8 permits: 1 Active, 1 Lapsed (STOP), 1 Suspended (STOP), ...` / `2 of 8 permits, state Active, type hot work`
def permit_page(detail, gas_tests, labels=None, technical=False, panel=False) -> Page   # identity `<key> · <subject>`, state line `Active · hot work · until 18:00 UTC` (Lapsed: `Lapsed · STOP, revalidate`; Suspended: `Suspended · STOP`), sections Where (area, location, for key), Work (holder, description), Approvals (requested by, approved by, issued by, ticked precautions count), Gas tests (newest first, at most 5: `Pass 14:05 UTC by <tester>` without readings; `none taken` when empty), History (revalidated n times, suspend reason, handback note, reject reason, cancel reason)
```
Counts in the summary come from the rows the log holds. Reading values (O2, LEL, H2S, CO) are not shown on this screen; the CLI shows them.

Log keys: `s` next state filter (the shown states, then all), `t` next type filter (`tl_mod_permits.types_table` names, read at runtime; all), `a` area filter cycle from the rows, `m` toggles `holder = the signed-in actor`, `F5` reload; Enter opens `PermitScreen`; hints `/ filter  s state  t type  a area  m mine  F5 reload  Esc back`.

`PermitScreen`: `Esc` back, `F5` reload, and these actions, each offered only in the states of the table (a state outside it offers nothing), each building the command with the screen's actor and scope as `widgets/receipt_entry.py::build_command` does (`permit = detail.row.id`, carried never shown; `expected_version = detail.version`) and sending it through `client.permit_command`, a refusal reaching the status line exactly as the punch and inspection screens do, then a reload:

| Key | Command | Offered in | Asks |
|---|---|---|---|
| `a` | ApprovePermit | Requested | "are you sure" |
| `x` | RejectPermit | Requested | reason |
| `s` | SuspendPermit | Active, Lapsed | reason |
| `r` | ResumePermit | Suspended | "are you sure" |
| `v` | RevalidatePermit | Active, Lapsed | "are you sure" |
| `h` | HandBackPermit | Active, Lapsed, Suspended | note (`handback_note`) |
| `c` | ClosePermit | Handed back | "are you sure" |

Issue, cancel and request stay on the CLI (issue needs ticked precautions, a gas test and verified isolations: a form of its own, follow-up). The decision whether a key is allowed is the server's: the screen never checks the requester, the approver or the gas test; it shows the refusal text. The state table above is the one place the screen knows states (the docstrings of `tl_mod_permits/commands.py`); it is a constant in `permit_text.py` with a test that pins it against those docstrings' states.

## Context (read these, nothing else)
- `docs/tickets/P2-INSP/T10-terminal.md`, `docs/reports/P2-IP/INSPT10.md`, `docs/reports/P2-IP/PTWT10.md`
- `packages/tl-tui/src/tl_tui/inspection_text.py`, `widgets/inspection_log.py` (merged by INSP-T10: the model; whole), `packages/tl-tui/tests/fakes_permits.py` (`seed_permits`), `test_inspection_screens.py` (the pilot pattern)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py`, `iso_views.py` (dataclasses only), `commands.py` (field names), `types_table.py` (names of the types)

## Allowed paths
- `packages/tl-tui/src/tl_tui/permit_text.py`, `packages/tl-tui/src/tl_tui/widgets/permit_log.py` (create)
- `packages/tl-tui/src/tl_tui/commands.py` (one `AppCommand("permits", "Permits to work: by state, type and area", "", "permits")` row), `packages/tl-tui/src/tl_tui/app.py` (the `permits` entry in the `screens` dict of `_push_awp`, its import, one `action_permits`)
- `packages/tl-tui/tests/test_permit_text.py`, `test_permit_screens.py`, `test_permit_nav.py` (create)
- consequential pins in union form, listed (rule 12): `packages/tl-tui/tests/test_palette.py`, `test_awp_nav.py`
- `docs/reports/P2-IP/PTWT11.md` (create)

## Tests to add
- `test_permit_text.py`: cells, summary and page lines for each state of `seed_permits`; Lapsed and Suspended pages say STOP in the state line; no 32-hex id; gas-test lines show no reading values; the state table equals the states in the command docstrings.
- `test_permit_screens.py` (pilot on `FakeClient`): mounts at 80 and 170 columns without overflow, Subject not right of the third column; `s`, `t`, `a`, `m` change the row count; Enter pushes `PermitScreen`; on a Requested permit `a` asks and sends `ApprovePermit` with the row id and version, `s` does nothing; on an Active one `s` asks a reason and sends `SuspendPermit`, `a` does nothing; on Suspended `r` sends `ResumePermit`; a refusal from the fake shows on the status line; `RecordNotFoundError` shows an error status, no traceback.
- `test_permit_nav.py`: the palette lists `permits`; choosing it shows `PermitLogScreen`.

## Acceptance
```
uv run ruff format --check packages/tl-tui/src/tl_tui packages/tl-tui/tests/test_permit_text.py packages/tl-tui/tests/test_permit_screens.py packages/tl-tui/tests/test_permit_nav.py
uv run ruff check packages/tl-tui/src/tl_tui packages/tl-tui/tests/test_permit_text.py packages/tl-tui/tests/test_permit_screens.py packages/tl-tui/tests/test_permit_nav.py
uv run pyright packages/tl-tui/src/tl_tui/permit_text.py packages/tl-tui/src/tl_tui/widgets/permit_log.py packages/tl-tui/src/tl_tui/commands.py packages/tl-tui/src/tl_tui/app.py packages/tl-tui/tests/test_permit_text.py packages/tl-tui/tests/test_permit_screens.py packages/tl-tui/tests/test_permit_nav.py
just gate packages/tl-tui/tests/test_permit_text.py packages/tl-tui/tests/test_permit_screens.py packages/tl-tui/tests/test_permit_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
A fact on a screen needs a field no row, detail or gas row carries (write which); the diff outside the two new files passes about 60 lines; a screen constructor or `LogScreen` needs a change; a command docstring states a state the table lacks.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. The `tui-layout` checklist answered line by line (7 lines). Commit subjects `P2-PTW-T11: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
