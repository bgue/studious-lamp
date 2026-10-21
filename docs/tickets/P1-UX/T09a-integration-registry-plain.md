# P1-UX-T09a — Integration registry: plain words, no ids

Status: ready (stage; dispatch after T07 is merged: both edit integration_text.py)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, T07 (merged)
Branch: `p1/ux-t09a-integration-registry-plain`

## Goal
The integration screen (apps, endpoints, rules, actions, enrichers, invocations, error queue) shows people and services by name or label, no invocation or delivery ids, no version numbers and no code versions, error codes and command names as words;
technical mode keeps today's text. The rows of this screen are projection rows, not records, so there is no Enter here (D15 reasoning; the enrichment values, which have a target record, are T07). The screen redraws on `refresh_for_display_mode` (D14).

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys, ids, hashes, versions, actor ids. Clause 3: technical shows what plain hides. D13: services by label via `actor_label`, never `svc:` ids. D14: `refresh_for_display_mode`. D27: pure functions keep raw output by default (`technical=True`).
> App, endpoint and rule names (`acme-nde`, `results`, `hse-notify`) are what a person types and chooses: they stay in both modes. T07 added `columns(kind, technical=)`, `state_words`, `property_words`, `record_name(ref, technical=)`, and the `technical` keyword on `cells` and `detail_lines` (enrichments only).

## Interfaces (verbatim from repo at T07's merge; re-read the file, these are today's)
```python
# tl_tui/integration_text.py
COLUMNS = {"apps": ("Name","State","Owner","Label"), "endpoints": ("Path","State","Mode","Auth","Access","Ver"), "rules": ("Key","State","Mode","Access","Ver","Title"),
           "actions": ("Name","State","Executor","Access","Approval","Ver","Label"), "enrichers": ("Name","State","Access","Ver","Code","Properties"),
           "invocations": ("Id","Status","Action","By","Requested"), "deliveries": ("Id","State","Endpoint","Received","Error"), "enrichments": (...)}
def on_off(row) -> str; def run_state(state) -> str; def short_id(v) -> str; def moment(stamp) -> str
def cells(kind, row, names=None, *, technical=True); def detail_lines(kind, row, names=None, *, technical=True)    # T07 added the flag; non-enrichment kinds ignore it
#   detail pairs today: endpoints "Acts as" service_actor, "Owner" owner, "Allowed" ", ".join(allowed_commands); rules "Acts as", "Owner", "Steps" ", ".join(step["command"]);
#   actions "Owner"; enrichers "Code" code_version, "Owner"; invocations "Invocation" id, "Action" f"{action} v{action_version}", "By" invoked_by;
#   deliveries "Delivery" id, "Endpoint" f"{name} v{endpoint_version}", "Error" f"{error_code}: {error_message}"
# widgets/integration_screen.py (today): IntegrationScreen(client, scope, actor, *, kind="endpoints"); KINDS = (endpoints rules actions enrichers apps invocations deliveries); self.rows self.names self.kind;
#   _fill(keep): table.clear(columns=True); table.add_columns(*COLUMNS[self.kind]); rows from cells(self.kind, row, self.names); _describe(): detail_lines(self.kind, row, self.names); _row_id(row) uses the *_id column (row key; keep it);
#   action_enable/disable status: f"{'Enabled' if enable else 'Disabled'} {cells(self.kind, row)[0]}"
# tl_tui/display.py: Labels, actor_label(labels, actor), humanize, mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types) (record_types=() loads the service labels too);  sample rows: tests/rows_integration.py (provided, final)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/integration_text.py`, `widgets/integration_screen.py`
- `packages/tl-tui/tests/test_integration_text.py`, `test_integration_screen.py`, `rows_integration.py` (read only)

## Allowed paths
- `packages/tl-tui/src/tl_tui/integration_text.py`, `packages/tl-tui/src/tl_tui/widgets/integration_screen.py`
- `packages/tl-tui/tests/test_integration_text.py`, `test_integration_screen.py`, `test_app_integration.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_integration_plain.py` (create)
- `docs/reports/P1-UX/T09a.md` (create)

## Steps
1. `cells` and `detail_lines` take `labels: Labels | None = None` (keyword, after `names`); plain, for the non-enrichment kinds:
   `columns(kind, technical=False)` drops `Ver` (endpoints, rules, actions, enrichers), `Code` (enrichers), `Id` (invocations, deliveries); cells drop the same values.
   Owner, `By`, `Acts as` use `actor_label(labels or Labels(), actor)`. Status and state words via `state_words` (T07). `Allowed` and `Steps` commands: `humanize` each. Error: `humanize(error_code)`. Action in invocation lines: the name without `v{n}`.
   The `Endpoint` line has the path without `v{n}`. The `Invocation`, `Delivery` and `Code` lines are dropped; `Error` reads `Mapping failed: no weld in the payload`.
2. `IntegrationScreen`: `self.labels = Labels()`; `on_mount` sets `self.labels = load_labels(self.client, self.scope, ())` before `reload()`. `_fill` and `_describe` read `technical = mode_of(self.app).technical`, take columns from `columns(self.kind, technical=technical)` and pass `labels=self.labels, technical=technical`.
   The enable/disable status uses the first cell as today (still the name for apps, endpoints, rules, actions, enrichers). `refresh_for_display_mode(self)`: `self._fill(<keep row id>)`.
3. Update pinned expectations that now read plain through the screen; keep one technical assertion per kind that lost a column or a line.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_integration_text.py packages/tl-tui/tests/test_integration_screen.py packages/tl-tui/tests/test_integration_plain.py packages/tl-tui/tests/test_app_integration.py packages/tl-tui/tests/test_embedded_integration.py packages/tl-tui/tests/test_embedded_integration_reserved.py packages/tl-tui/tests/test_review_queue.py packages/tl-tui/tests/test_review_plain.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_integration_plain.py` (new, this ticket creates it) and `test_review_plain.py` (created by T07, must be merged first). Expected `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_integration_plain.py` (as `test_integration_screen.py` builds its world):
- `test_plain_columns_and_cells_drop_ids_versions_and_code_versions` (pure; each kind that changed).
- `test_plain_detail_lines_name_services_and_hide_ids` (`svc:` -> label / `a service`; `find_technical(text) == []` over every kind's panel).
- `test_technical_detail_lines_are_unchanged` (technical output equals the pre-ticket text for one row of every kind).
- `test_screen_redraws_columns_on_the_mode_switch` (flag on, refresh, `Ver` column back; off).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- A plain value still shows an id, `svc:`, `user:` or a version: list it; fix only inside Allowed paths.
- A screen test depends on the `Id` column to find a row: use the row key; stop if that needs the fake changed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
