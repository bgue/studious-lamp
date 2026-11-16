# P2-I4B-T07b — Scaffold register, record view and their palette entry

Status: staged (dispatch after T09b2 and T07a merge; refine from their reports)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T09b2 (client methods, fake), T07a (palette and `app.py` toolcrib wiring)
Branch: `p2/i4b-t07b-scaffold-screens`
Worktree: `/home/user/wt/i4b/t07b` (from `p2/i4b` head)

## Goal
A scaffold register screen (what stands, its state, tag colour, when the next inspection is due) and a record screen for one scaffold with its inspections, both read-only over the T09b2 client methods, plus the palette entry `scaffolds` and `action_scaffolds` (no key). This is the plan's T07a "TUI scaffold register and record view"; the plan's report row "scaffold register report" is the export (`export_scaffolds`), reachable here by one key. The state-changing acts (register, design, erect, inspect, tag, release, modify, dismantle, remove) stay on the command door and the generic record actions; no write screen here. Skill `tui-layout` applies (load it): labels left, words not codes, `—` for an empty value, narrow-width drop order.

## Interfaces
`tl_tui/scaffold_text.py` (new, Textual-free, no client call; model `punch_text.py`): `SCAFFOLD_COLUMNS = ("Number", "Subject", "State", "Tag", "Last inspected", "Next due", "Location")`, drop order at narrow width (Location, Last inspected, Subject), `register_page(rows, total, *, today, labels)` (the log text and a summary line "N scaffolds: 2 In Use, 1 Modify; 1 overdue", overdue = standing state and `next_due_on < today`, computed from `today` passed in, never the clock), `detail_page(detail, *, labels)` (identity line, state line, property:value lines Tag, Tagged on, Last inspected, Next due, Location, Elevation, Gridline, Load class, Requested from, Serves; Modify and Dismantle reasons when present; an Inspections section oldest first: date, inspector, result in words, tag, note), `export_filename(project, fmt)`. Tag colour words are green, yellow, red as text, never colour alone. Dates through `tl_tui.awp_text.date_text`.
`widgets/scaffold_register.py`: `ScaffoldLogScreen(client, project)` (Enter opens `ScaffoldScreen(client, project, key)`; `s` cycles the state filter, `o` toggles overdue only, `x` writes the export of the visible filter to `./scaffolds-<project>.csv` and says so on the status line, `X` the JSONL; Esc closes) and `ScaffoldScreen` (inspections list; Esc back). Reads under `CLIENT_ERRORS` with `describe_error`; a missing or hidden key shows one text "No such scaffold." (the client raises one text for both).

## Context (read these, nothing else)
- `docs/reports/P2-I4B/{T09b2,T07a}.md`, `packages/tl-modules/scaffold/src/tl_mod_scaffold/views.py` (dataclasses only), `packages/tl-tui/src/tl_tui/punch_text.py`, `widgets/punch_log.py`, `tests/test_punch_screens.py`, `tests/test_punch_nav.py`, `.claude/skills/tui-layout/SKILL.md`
- `packages/tl-tui/tests/fakes_scaffold.py` (`seed_scaffolds`), `app.py` (`_push_awp` table, one entry plus one action), `commands.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/scaffold_text.py`, `widgets/scaffold_register.py` (create); `commands.py` (one row), `app.py` (the `_push_awp` table entry and `action_scaffolds`)
- consequential pins (union form, listed): `test_palette.py`, `test_awp_nav.py`
- `packages/tl-tui/tests/test_scaffold_text.py`, `test_scaffold_screens.py`, `test_scaffold_nav.py` (create); `docs/reports/P2-I4B/T07b.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_scaffold_text.py packages/tl-tui/tests/test_scaffold_screens.py packages/tl-tui/tests/test_scaffold_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```

## Tests to add
Text: columns, drop order, summary counts with a fixed `today`, an empty register, a detail with and without inspections and reasons, no `—` typed into a field, ids never printed. Screens (pilot on `FakeClient` + `seed_scaffolds`, widths 80 and 170): the register lists the seeded rows, `s` and `o` narrow them, Enter opens the record and Esc returns, `x` writes a CSV under `tmp_path` (cwd patched) whose first line is the export header, a client error shows its text. Nav: the palette lists `scaffolds` and opens the log.

## Escalation triggers
- A view field the screen needs is missing (write which); the diff passes about 400 lines (split text and screens, tell the supervisor).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4B-T07b: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
