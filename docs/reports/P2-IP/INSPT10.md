# Report — P2-INSP-T10

Branch: `p2/insp-t10-terminal`   Commits: `9ba9d1c3` (failed answers on the detail, the ruling), `091bbbbd` (terminal screens, palette), then the report commit.

## Deviations
- Scope extended by the ruling: `insp_views.py`, `test_insp_views.py`, `docs/reference/openapi.json` (regenerated), `tests/fakes_insp.py`. Nothing else outside the ticket's paths.
- Base is `229bc67b` per the dispatch, not `p2/ip-r3`. This report replaces the blocked report in `dc6a4485`.
- `InspectionDetail.failed` is computed in the detail's own statement: a join to the pinned checklist's `questions_json`, filtered by the viewer, then `insp_rules.failed_questions`. No extra statement.
- Result cell reads `-` when none, as the ticket says. The tui-layout skill says never show `-`; see Open questions.
- Result and point values print as stored (`reject`, `hold`), as the ticket's state-line example does. The state is humanized.
- A refusal reloads the inspection screen (ticket). The punch screen does not reload on refusal.
- A checklist the viewer may not read joins to nothing, so `failed` is `[]` for it.
- The ticket's acceptance `ruff`/`pyright` lines are covered by the lite gate (`ruff check .`, `ruff format --check .`, pyright on changed files). Committed first, because the lite gate checks the committed diff.

## Changed files
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` — `FailedAnswer`; `failed` on `InspectionDetail`.
- `packages/tl-modules/quality/tests/test_insp_views.py` — two view tests for `failed`.
- `docs/reference/openapi.json` — regenerated (additive: `FailedAnswer`, `failed`).
- `packages/tl-tui/tests/fakes_insp.py` — one failed answer seeded on inspection 3.
- `packages/tl-tui/src/tl_tui/inspection_text.py` (new) — cells, summary, page.
- `packages/tl-tui/src/tl_tui/widgets/inspection_log.py` (new) — `InspectionLogScreen`, `InspectionScreen`.
- `packages/tl-tui/src/tl_tui/commands.py`, `app.py` — `inspections` row, screens entry, `action_inspections`.
- `packages/tl-tui/tests/test_inspection_text.py`, `test_inspection_screens.py`, `test_inspection_nav.py` (new).

## Commands and output
```
$ uv run python -m tl_api.openapi            -> wrote docs/reference/openapi.json
$ uv run python -m tl_api.openapi --compat   -> exit 0
$ bash lite-gate.sh /home/user/wt/ip4/inspt10 229bc67b <the five TUI test files>
ruff: ok
format: ok
pyright (changed files): 0 errors, 0 warnings, 0 informations
generate: ok
compat: ok
openapi: ok
licences: ok
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
- `test_insp_views.py::test_a_failing_required_answer_is_listed_by_question_text_and_note` — `failed == [("Gauge fitted?", "Gauge missing")]`.
- `test_insp_views.py::test_a_passing_or_unrecorded_inspection_has_no_failed_answers` — `[]` for Verified and Planned.
- `test_inspection_text.py` (9) — cells per state, summary and filter line, state lines, Result failed line by text, punch keys, no 32-hex id, pinned plan and history lines.
- `test_inspection_screens.py` (14) — 80 and 170 columns, `s`/`p`/`m` counts, Enter, `v` on Done sends Verify with row id and version, `v` on Planned does nothing, `x` sends Cancel, `r` with no date sends `planned_on=None`, refusal on the status line, unknown key gives an error status.
- `test_inspection_nav.py` (1) — palette lists `inspections`; choosing it shows the log.
- `test_palette.py`, `test_awp_nav.py` needed no change.

## tui-layout checklist (skill has nine items)
1. Glance: breadcrumb, key and title, state line, keys row — yes.
2. Identity line first; other values are `Label  value`; no stray values — yes.
3. Sections Where, Plan, Result, History, Punch, one blank line apart — yes.
4. Technical tier: Version is shown only in technical mode.
5. Log columns Number, Title, State first; Point and Result vary; no sideways scroll at 170 — yes.
6. Panel: summary line under the state; Inspector appears in the summary and in Plan (as the punch page does).
7. Empty values `—` in fixed sections; Punch shows "No punch items" — yes.
8. Labels match the punch screens' conventions; no sibling inspection screen exists yet.
9. 80 and 170 columns tested; no line over the width.

## Learnings (proposed)
- The ticket's "failed answers are the dicts whose result is fail" does not match stored data. Answers are `{q, value, note}`; failure needs the pinned checklist's questions. A spec for the detail should say so.
- The lite gate's pyright covers only files in `git diff base...HEAD`. Commit before gating.
- `ruff format` on the tree rewrites files read earlier; re-read before editing them.

## Open questions / Blocked
- Result cell: ticket says `-` when none; tui-layout says `—` (never `-`). I followed the ticket. Supervisor to pick one.
