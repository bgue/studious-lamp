# P2-INSP-T10 - Terminal: `inspection_text.py`, the inspection log and record screen, palette glue

Status: ready (written r6; base `p2/ip-r3`; INSP-T08 merged: client methods, fake, `quality_command` for the eleven commands)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: P2-INSP-T08 (merged)
Branch: `p2/insp-t10-terminal`
Worktree: `/home/user/wt/insp/t10` (from `p2/ip-r3`)

## Goal
`tl_tui/inspection_text.py` (Textual-free), `InspectionLogScreen(client, project)` and `InspectionScreen(client, project, key)` in `tl_tui/widgets/inspection_log.py`, reachable from the palette by id `inspections`. No business logic: the screens call `list_inspections`, `get_inspection` and, for three actions, `quality_command`. Model: `punch_text.py`, `widgets/punch_log.py`, `docs/tickets/P2-PUNCH/T06-tui-punch-log.md` (read it; its structure is this ticket's). Load the `tui-layout` skill. Scheduling and recording answers stay on the CLI until the runner screen (follow-up T11); the screen says so in its key hints, not in code.

## Interfaces (create; names exact)
```python
# inspection_text.py
INSPECTION_COLUMNS = ("Number", "Title", "State", "Point", "Result", "Scheduled", "Inspector", "Area")
INSPECTION_DROP = ("Inspector", "Area", "Scheduled"); INSPECTION_RIGHT = ()
def inspection_cells(row, labels=None) -> tuple[str, ...]      # Scheduled via awp_text.date_text; Inspector via actor_label; Result "-" when None
def inspection_summary(counts_or_rows, total, shown, *, state=None, point=None) -> str   # `9 inspections: 2 Planned, 3 Scheduled, 2 Done, 1 Verified, 1 Cancelled` / `2 of 9 inspections, state Done, point hold`
def inspection_page(detail, labels=None, technical=False, panel=False) -> Page   # identity `<key> · <title>`, state line `Done · hold point · reject`, sections Where (subject key, work package key, area), Plan (planned on, scheduled for, inspector, checklist key and version), Result (recorded by and on, note, one line per failed answer: question text and note; verified by and on), History (reinspection of, cancel reason), Punch (the keys in detail.punch_keys)
```
The summary counts come from the rows the log holds (`total` is the page total); do not add a counts method. Failed answers are the dicts of `detail.answers` whose result is `fail` (read the shape from `insp_rules.failed_questions` or `insp_views`; show question text, never an index or id).

Log keys: `s` next state filter (Planned, Scheduled, Done, Verified, Cancelled, all), `p` next point filter (hold, witness, review, surveillance, all), `m` toggles `inspector = the signed-in actor`, `F5` reload; Enter opens `InspectionScreen`; `KEY_HINTS` `/ filter  s state  p point  m mine  F5 reload  Esc back`. `InspectionScreen`: `Esc` back, `F5` reload; `v` Verify (asks "are you sure"), `r` Reinspect (asks an optional date, `YYYY-MM-DD`), `x` Cancel (asks a reason). Each key shows only for the states `tl_mod_quality.actions.RULES` offers it in (`VerifyInspection` on Done, `ReinspectInspection` on Done or Verified, `CancelInspection` on Planned or Scheduled; read the rows, do not copy them) and builds the command with the screen's actor and scope as `widgets/receipt_entry.py::build_command` does (`inspection` = `detail.row.id`, carried never shown; `expected_version = detail.version`). A refusal (the recorder verifying) reaches the status line through the `LogScreen.attempt`-style handling the punch screen uses, then the screen reloads. An inspection is never shown by id.

## Context (read these, nothing else)
- `docs/tickets/P2-PUNCH/T06-tui-punch-log.md`, `packages/tl-tui/src/tl_tui/punch_text.py`, `packages/tl-tui/src/tl_tui/widgets/punch_log.py` (the model; both whole)
- `packages/tl-tui/tests/fakes_insp.py` (T08: `seed_inspections`), `packages/tl-tui/tests/test_punch_screens.py`, `test_punch_nav.py` (the pilot pattern)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (dataclasses only), `actions.py` (`RULES`, names)
- `docs/reports/P2-IP/INSPT08.md`

## Allowed paths
- `packages/tl-tui/src/tl_tui/inspection_text.py`, `packages/tl-tui/src/tl_tui/widgets/inspection_log.py` (create)
- `packages/tl-tui/src/tl_tui/commands.py` (one `AppCommand("inspections", "Inspections: by state and point", "", "inspections")` row), `packages/tl-tui/src/tl_tui/app.py` (the `inspections` entry in the `screens` dict of `_push_awp`, its import, one `action_inspections`)
- `packages/tl-tui/tests/test_inspection_text.py`, `test_inspection_screens.py`, `test_inspection_nav.py` (create)
- consequential pins in union form, listed (rule 12): `packages/tl-tui/tests/test_palette.py`, `test_awp_nav.py`
- `docs/reports/P2-IP/INSPT10.md` (create)

## Tests to add
- `test_inspection_text.py`: cells, summary and page lines for each state of `seed_inspections`; no 32-hex id in any line; the Result section lists failed questions by text; the punch keys appear.
- `test_inspection_screens.py` (pilot on `FakeClient`): mounts at 80 and 170 columns without overflow, Title not right of the third column; `s`, `p`, `m` change the row count; Enter pushes `InspectionScreen`; on a Done inspection `v` asks and sends `VerifyInspection` with the row id and the version, on a Planned one `v` does nothing and `x` asks a reason and sends `CancelInspection`; a refusal from the fake shows on the status line; `RecordNotFoundError` shows an error status, no traceback.
- `test_inspection_nav.py`: the palette lists `inspections`; choosing it shows `InspectionLogScreen`.

## Acceptance
```
uv run ruff format --check packages/tl-tui/src/tl_tui packages/tl-tui/tests/test_inspection_text.py packages/tl-tui/tests/test_inspection_screens.py packages/tl-tui/tests/test_inspection_nav.py
uv run ruff check packages/tl-tui/src/tl_tui packages/tl-tui/tests/test_inspection_text.py packages/tl-tui/tests/test_inspection_screens.py packages/tl-tui/tests/test_inspection_nav.py
uv run pyright packages/tl-tui/src/tl_tui/inspection_text.py packages/tl-tui/src/tl_tui/widgets/inspection_log.py packages/tl-tui/src/tl_tui/commands.py packages/tl-tui/src/tl_tui/app.py packages/tl-tui/tests/test_inspection_text.py packages/tl-tui/tests/test_inspection_screens.py packages/tl-tui/tests/test_inspection_nav.py
just gate packages/tl-tui/tests/test_inspection_text.py packages/tl-tui/tests/test_inspection_screens.py packages/tl-tui/tests/test_inspection_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
A fact on a screen needs a field no row or detail carries (write which); the diff outside the two new files passes about 60 lines; a screen constructor or `LogScreen` needs a change; `RULES` has no row for a command named above.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins listed. The `tui-layout` checklist answered line by line (7 lines). Commit subjects `P2-INSP-T10: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
