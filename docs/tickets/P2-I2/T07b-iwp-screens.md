# P2-I2-T07b — IWP text module, IWP log and IWP screen

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, read, confidentiality
Depends on: T04c2
Branch: `p2/i2-t07b-iwp-screens`
Worktree: harness-created under `/home/user/wt/i2/t07b` (from `p2/i2` head)

## Goal
`tl_tui/iwp_text.py` (Textual-free; TW1 reuses it), `IwpRegisterScreen(client, project)` (the module's home log) and `IwpScreen(client, project, number)` (one IWP: summary, scope, sign-offs, pins, constraint count). Models: P2-I1 T05a/T05d and `widgets/cwp_register.py`; skill `tui-layout`.
Scope cuts (D33): the log has no Ready (`5/7`) and Constraints (open) columns, and the IWP screen has no Readiness or Constraints tab: `IwpRow` carries neither and a read per row is not allowed. T07c (after T04b and T07a) adds the keys that open the readiness screen and the IWP's constraint log from the IWP screen; the list-level counts are a follow-up read.

## Brief references (pasted; module design "IWP log")
> Columns: Number, Subject, State, Discipline, Foreman, Planned start, Ready, Constraints, Hours. Filters: `m` mine (foreman), `r` Ready only, by CWA. Panel: identity `P123-IWP-PIP-0042 · Rack 12 tie-ins`; state `Constraint check · since 2026-10-28`; summary `Piping · crew J. Soto · 2026-11-03 to 11-14 · 420 h`. Sections: Scope (counts by commodity), Drawings (pinned count), Timeline.
Reads (T04c2): `list_iwps(project, state=, discipline=, foreman=, limit=)` -> `IwpRow` (id number title state discipline planned_start planned_finish foreman estimated_hours cwp_number scope_count); `get_iwp(project, number)` -> `IwpDetail` (+ crew_text signoffs pin_count open_constraints scope_by_type); `list_iwp_scope(project, number, limit=)` -> `ScopeRow`.

## Interfaces (create; names exact)
```python
# iwp_text.py
IWP_COLUMNS = ("Number", "Subject", "State", "Discipline", "Foreman", "Planned start", "Scope", "Hours")
IWP_DROP = ("Planned start", "Foreman", "Discipline"); IWP_RIGHT = ("Scope", "Hours")
def iwp_cells(row, labels=None) -> tuple[str, ...]     # Hours via awp_text.hours_text, Planned start via awp_text.date_text, Foreman actor_label
def iwp_summary(total, shown, *, state=None, foreman=None) -> str   # `7 IWPs` / `3 of 7 IWPs, state Ready`
def iwp_page(detail, scope_rows, labels=None, technical=False, panel=False) -> Page   # identity, state line, summary line, sections Scope (by type, then up to 10 rows when panel else 50), Sign-offs (who, when), Drawings (`<n> pinned`), Constraints (`<n> open`)
```
Import `hours_text`, `date_text` from `tl_tui.awp_text`; do not copy them. Keys of the log: `s` next state, `d` next discipline, `m` toggles `foreman = the signed-in actor`, `r` toggles state Ready, `F5`; Enter opens `IwpScreen`; `KEY_HINTS` `/ filter  s state  d discipline  m mine  r ready  F5 reload  Esc back`. `IwpScreen`: Esc back, `F5`, text only (no actions here: `actions_for` returns `[]`).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` lines 1-130 and 270-274, `widgets/cwp_register.py` (all), `widgets/log_screen.py` lines 96-225, `widgets/record_screen.py` lines 1-60
- `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` lines 41-79, `tests/fakes_iwp.py` (`seed_iwp`), `tests/helpers.py` lines 1-60

## Allowed paths
- `packages/tl-tui/src/tl_tui/iwp_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/iwp_register.py` (create; holds both screens)
- `dev/accept/P2-I2/T07b.py` (create), `docs/reports/P2-I2/T07b.md` (create)
Palette and nav entries are glue (T07c).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T07b.py            # no pytest
```
`T07b.py` (Textual pilot on `FakeClient` + `seed_iwp`): `PASS mount 80` and `PASS mount 170` (no overflow; Subject not right of the third column; panel at 170 shows identity, state, summary); `PASS keys` (`s`, `d`, `m`, `r` change the row count as filters; `m` uses the actor); `PASS enter` (Enter pushes `IwpScreen` for that number; its page shows scope by type and `<n> open` constraints); `PASS missing` (`RecordNotFoundError` from `get_iwp` -> error status, no traceback); `PASS words` no 32-hex id in any line. Ends `T07b ok`.

## Escalation triggers
- Stop if a fact on a screen needs a field no row or detail carries (write which); never read per row.

## Tests to add
None (S5 / T-screens twins hold the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the `tui-layout` checklist answered line by line (7 lines). Subject `P2-I2-T07b: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
