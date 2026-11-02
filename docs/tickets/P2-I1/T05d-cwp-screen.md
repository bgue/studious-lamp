# P2-I1-T05d — CWP register screen

Status: ready (after T05a merged)
Tier: haiku
Review: full
Labels: tui
Depends on: T05a
Branch: `p2/i1-t05d-cwp-screen`
Worktree: `/home/user/wt/i1/t05d` (from `p2/i1` head)

## Goal
The CWP register as a `LogScreen` (spec §8, skill `tui-layout`) over `tl_tui/awp_text.py` (T05a, merged): the log, the panel (`cwp_page(panel=True)`), the keys, Enter to the record screen.
It holds no logic of its own: columns, cells, summary and page all come from `awp_text`. No actions bar entries in I1 (writes come with P2-I2): `actions_for` returns `[]`.

## Interfaces (in the tree; T05a adds `awp_text`)
```python
# awp_text (T05a): CWP_COLUMNS CWP_DROP CWP_RIGHT cwp_cells(row, labels) cwp_summary(detail) cwp_page(detail, labels, technical=, panel=) group_by_cwa(rows)
# client: list_cwps(project, *, state=, discipline=, cwa=) -> list[CwpRow]; get_cwp(project, number) -> CwpDetailView; errors: tl_tui.errors CLIENT_ERRORS, describe_error
# LogScreen[Row] hooks and the pattern: widgets/tag_register.py (all 174 lines): ctor (client, project); log_project columns drop_order load_rows row_key row_cells row_record panel_text actions_for
#  summary_text open_row; BINDINGS Binding("d", "discipline", ..., show=False); action_* cycle a filter and call self._fill(); labels via tl_tui.labels_load.load_labels; mode_of(self.app).technical
# layout.render(page) -> Adaptive for panel_text; tl_tui.widgets.record_screen.open_record(self, client, scope, project, actor, record_id)
```
Keys: `d` next discipline (all, then each present), `s` next state, `c` toggles grouping by CWA (`group_by_cwa`: a heading row per CWA is NOT added; the rows are ordered by CWA then number and the CWA column shows).
`KEY_HINTS`/`KEY_CELLS`/`HELP_KEYS` name `/ filter  d discipline  s state  c by CWA  F5 reload  Esc back`. The summary line: `n CWPs` or `n of m CWPs` with the filters named.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (all), `packages/tl-tui/src/tl_tui/awp_text.py` (names only)
- `packages/tl-tui/src/tl_tui/widgets/log_screen.py` lines 96-225; `packages/tl-tui/tests/helpers.py` lines 1-60; `packages/tl-tui/tests/fakes_awp.py` (`seed_awp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/cwp_register.py` (create), `dev/accept/P2-I1/T05d.py` (create), `docs/reports/P2-I1/T05d.md` (create)
Nav entry ("Work packaging" > "CWPs") and palette entry are supervisor glue (`nav_tree.py`, `app.py`).

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/T05d.py                        # no pytest
```
`T05d.py` (the screen on `FakeClient` + `seed_awp` through the Textual pilot, as `tests/helpers.py` does): `PASS mount 80` and `PASS mount 170` (no line wider than the terminal; Subject not right of the third column;
at 170 the panel shows the heading, the state and a summary line); `PASS keys` (`d` and `s` change the row count, `c` orders by CWA); `PASS enter` (Enter calls `open_record` once: patch it); `PASS missing`
(a `RecordNotFoundError` from `get_cwp` shows an error status, not a traceback). Ends `T05d ok`.

## Tests to add
none (T11: `packages/tl-tui/tests/test_cwp_register.py`, 80 and 170 columns).

## Report requirements
`docs/reports/P2-I1/T05d.md` <= 60 lines; deviations first; tui-layout checklist answered line by line (7 lines). Subject `P2-I1-T05d: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a fact on the screen needs a field no view carries (write which); never read per row.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
