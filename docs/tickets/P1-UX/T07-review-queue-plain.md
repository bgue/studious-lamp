# P1-UX-T07 — Review queue: Enter opens the record, plain words for proposed values

Status: ready (stage; T09a follows it, both edit integration_text.py)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2 (merged)
Branch: `p1/ux-t07-review-queue-plain`

## Goal
In the review queue (Ctrl+R) Enter on a proposed value opens the full record screen of the record the value is about (`row["target"]["id"]`, Q4 closed r3); Esc returns on the same row.
Plain mode shows no value id, no enricher version and no property path: states read `Waiting`, `Accepted`, `Rejected`; the property is `Doc type`, not `documents.doc_type`; the record is its key (`(no number)` when it has none).
Technical mode keeps today's text. The screen redraws on `refresh_for_display_mode` (D14). The other integration kinds are T09a; this ticket adds the shared `technical` switch to `integration_text.py` and uses it for `enrichments` only.

## Brief references (pasted)
> SCOPE clause 1: Enter on any row opens the full record view; Esc returns on the same row. Clause 2: plain words; no internal keys, ids, hashes, versions. Clause 3: technical shows what plain hides. D22: open on `DataTable.RowSelected`. D14: `refresh_for_display_mode`.
> D27: pure functions keep raw output by default (`technical=True`); the screen passes the mode explicitly.
> Q4: enrichment rows are `EnrichmentValue` dumps with `target` = RecordRef dict `{id, key, record_type, version, seq}`.

## Interfaces (verbatim from repo)
```python
# tl_tui/integration_text.py (today; enrichments parts)
COLUMNS["enrichments"] = ("Id", "State", "Record", "Property", "Value", "Conf")
def run_state(state: object) -> str       # "✓ {state}" for completed/applied/accepted/auto_accepted; "! {state}" for failed/killed/rejected; else "… {state}"
def short_id(value) -> str                # last 8 chars
def record_name(ref) -> str               # ref["key"] or ref["id"] or "?"
def cells(kind, row, names=None) -> tuple[str, ...]      # enrichments: (short_id(value_id), run_state(acceptance_state), record_name(target), property_path, shown_value(value), f"{confidence:.2f}")
def detail_lines(kind, row, names=None) -> list[str]     # enrichments pairs: Value (value_id), State, Record, Property, Proposed, Confidence, Enricher (f"{enricher}@{enricher_version}"), Produced, Reason (if set); f"{label:<12}{value}"
# widgets/review_queue.py (today): ReviewQueueScreen(client, scope, actor); self.values: list[dict]; table "#review-table" (row key = value_id); WAITING = "proposed";
#   on_mount adds columns COLUMNS["enrichments"]; _fill builds rows with cells("enrichments", value); _describe uses detail_lines("enrichments", value);
#   status texts: f"This value is already {acceptance_state}.", f"Accepted {property_path}", f"Rejected {property_path}", PromptScreen(f"Reject {property_path}", "Reason", required=True)
# widgets/record_screen.py: open_record(screen, client, scope, project, actor, record_id);  project = project_of_scope(scope) or ""  (tl_core.settings.layers)
# tl_tui/display.py: humanize, mode_of(app).technical;  sample rows: tests/rows_integration.py (provided, final; `enrichment(**over)`)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/integration_text.py` (lines 1-100 and 140-221), `widgets/review_queue.py`
- `packages/tl-tui/tests/test_review_queue.py`, `test_integration_text.py`, `rows_integration.py` (read only)

## Allowed paths
- `packages/tl-tui/src/tl_tui/integration_text.py`, `packages/tl-tui/src/tl_tui/widgets/review_queue.py`
- `packages/tl-tui/tests/test_review_queue.py`, `test_integration_text.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_review_plain.py` (create)
- `docs/reports/P1-UX/T07.md` (create)

## Steps
1. `integration_text`: add `PLAIN_ENRICHMENT_COLUMNS = ("State", "Record", "Property", "Value", "Confidence")`; `columns(kind, *, technical=True)` returns `COLUMNS[kind]` when technical or the kind is not `enrichments`, else the plain tuple. `COLUMNS` itself does not change.
   Add `state_words(state, *, technical)`: technical = `run_state(state)`; plain keeps the symbol and humanizes (`✓ Accepted`, `! Rejected`, `… Waiting`; the stored state `proposed` reads `Waiting`; `auto_accepted` reads `Accepted automatically`). Add `property_words(path)`: `humanize(path.rpartition(".")[2])`. `record_name(ref, *, technical=True)`: plain `key` else `(no number)`.
2. `cells(kind, row, names=None, *, technical=True)` and `detail_lines(kind, row, names=None, *, technical=True)`: technical (default) = today's text for every kind. Plain, `enrichments` only: cells `(state_words, record_name, property_words, shown_value, confidence)`;
   detail pairs drop `Value` (id), show `Enricher` as `humanize(row["enricher"])` without the version, `Property` via `property_words`, `State` via `state_words`, `Record` via plain `record_name`. All other kinds ignore the flag for now (T09a).
3. `ReviewQueueScreen`: `technical = mode_of(self.app).technical` in `on_mount`, `_fill` and `_describe`; columns come from `columns("enrichments", technical=technical)` and are rebuilt in `_fill` (`table.clear(columns=True)` then `add_columns`); remove the column add from `on_mount` (reload does it).
   Status and prompt texts use `property_words` in plain and `humanize(acceptance_state)` in the "already" line. `on_data_table_row_selected`: `event.stop()`; guard the index; `open_record(self, self.client, self.scope, project_of_scope(self.scope) or "", self.actor, value["target"]["id"])`.
   `refresh_for_display_mode(self)`: `self._fill(<keep value_id>)`.
4. Update pinned expectations that now read plain through the screen; keep one technical assertion for the id column and the version.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_review_queue.py packages/tl-tui/tests/test_review_plain.py packages/tl-tui/tests/test_integration_text.py packages/tl-tui/tests/test_integration_screen.py packages/tl-tui/tests/test_app_integration.py packages/tl-tui/tests/test_embedded_integration.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_review_plain.py` (new, this ticket creates it). Expected `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_review_plain.py` (as `test_review_queue.py` builds its world; `client.add_stored_record(<target id>, <target key>, "documents.Document", <title>)`):
- `test_enter_on_a_value_opens_the_target_record_and_escape_returns_to_the_same_row`.
- `test_a_target_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the text).
- `test_plain_table_and_panel_have_no_id_version_or_property_path` (`find_technical(text) == []`, no `@`, no `documents.`).
- `test_technical_mode_restores_the_id_the_version_and_the_path_and_back`.
- `test_plain_cells_and_detail_lines_for_waiting_accepted_rejected_states` (pure functions).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- A value row has no `target` (older fake): guard and report; do not change `rows_integration.py`.
- `add_stored_record` does not make the record screen open: stop.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
