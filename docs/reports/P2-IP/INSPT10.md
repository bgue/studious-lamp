# Report — P2-INSP-T10

Branch: `p2/insp-t10-terminal`   Commits: `9ba9d1c3` (failed answers on the detail, the ruling), `091bbbbd` (terminal screens, palette), `a6c67f68` (this report).

## Deviations
- Scope extended by the ruling: `insp_views.py`, `test_insp_views.py`, `docs/reference/openapi.json` (regenerated), `tests/fakes_insp.py`.
- Base is `229bc67b` per the dispatch, not `p2/ip-r3`. This report replaces the blocked one in `dc6a4485`.
- `failed` is computed in the detail's own statement (a join to the pinned checklist's questions, viewer-filtered, then `insp_rules.failed_questions`). No extra statement; a checklist the viewer may not read gives `[]`.
- Result cell reads `-` when none, as the ticket says (tui-layout says `—`; see Open questions).
- Result and point print as stored (`reject`, `hold`), as the ticket's state-line example does.
- A refusal reloads the inspection screen (ticket); the punch screen does not.
- Ticket ruff and pyright lines are covered by the lite gate (committed first; it checks the committed diff).

## Changed files
- `insp_views.py` — `FailedAnswer`; `failed` on `InspectionDetail`.
- `test_insp_views.py` — two tests for `failed`.
- `docs/reference/openapi.json` — regenerated (additive).
- `tests/fakes_insp.py` — one failed answer seeded on inspection 3.
- `tl_tui/inspection_text.py`, `tl_tui/widgets/inspection_log.py` (new); `commands.py`, `app.py` (palette row, screens entry, `action_inspections`).
- `tests/test_inspection_text.py`, `test_inspection_screens.py`, `test_inspection_nav.py` (new).

## Commands and output
```
$ uv run python -m tl_api.openapi            -> wrote docs/reference/openapi.json
$ uv run python -m tl_api.openapi --compat   -> exit 0
$ bash lite-gate.sh <wt> 229bc67b <five TUI test files>
ruff: ok / format: ok / pyright (changed files): 0 errors / generate, compat, openapi, licences: ok
part 1: exit 0, 68 passed in 23.39s
gate: PASS
$ just gate packages/tl-modules/quality/tests/test_insp_views.py
part 1: exit 0, 22 passed in 32.10s
gate: PASS
$ just gate packages/tl-api/tests/test_api_insp.py
part 1: exit 0, 15 passed in 9.16s
gate: PASS
```

## Tests added
- `test_insp_views.py`: failing required answer gives `[("Gauge fitted?", "Gauge missing")]`; a passing or unrecorded one gives `[]`.
- `test_inspection_text.py` (9): cells per state, summary, state lines, failed line by text, punch keys, no 32-hex id, pinned plan and history.
- `test_inspection_screens.py` (14): 80 and 170 columns, `s`/`p`/`m` counts, Enter, `v`/`x`/`r` per state, refusal on the status line, unknown key gives an error status.
- `test_inspection_nav.py` (1): palette lists `inspections` and opens the log.
- `test_palette.py`, `test_awp_nav.py`: no change needed.

## tui-layout checklist (nine items)
Glance, identity line, sections, tiers, columns, panel summary, empty values, labels, 80/170 widths: all yes. Version is technical-only. Inspector appears in the panel summary and in Plan, as on the punch page.

## Learnings (proposed)
- The ticket's "failed answers are dicts whose result is fail" does not match stored data: answers are `{q, value, note}`, and failure needs the pinned checklist's questions. A detail spec should say so.
- The lite gate's pyright covers only files in `git diff base...HEAD`: commit before gating.
- `ruff format` on the tree rewrites files read earlier; re-read before editing.

## Open questions / Blocked
- Result cell: the ticket says `-` when none; tui-layout says `—`. I followed the ticket. Supervisor to choose.
