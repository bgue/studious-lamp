# P1-UX-T08 — Record view header and History, context panel: plain words

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t08-record-view-context`

## Goal
The record view (opened from the grid and used inside RecordScreen) and the right-hand context panel show no internal tokens by default.
Header: `v{version}` is hidden in plain, shown in technical (D20). History tab: plain columns `When | What | By | Summary` (event type as a word, actor as a name, no layer, property names as words);
technical keeps `# | When | Event | Actor | Summary` as today. Context panel: no `v{version}`, no schema hash, type as its label, `Properties` heading, property names as words; technical keeps today's text.
Both redraw on `refresh_for_display_mode` (D14). (The Links, Thread tabs and the grid are T08b and T08c.)

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys, ids, hashes, schema versions, actor ids. Clause 3: technical mode shows what plain hides. D20: record header `v{version}` hidden in plain, shown in technical.
> D14: `refresh_for_display_mode(self) -> None`. D27: functions another ticket calls keep their raw output by default (`technical=True`); the widget passes the mode explicitly.
> The History tab is in the walking test's scan (find_technical): no `Record.Created`, `user:`/`svc:`, ids, hashes, `psets.` paths in plain.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/record_view.py (today)
def event_summary(event: Event) -> str:   # kinds: Record.Created "created: {title}", Record.Updated "changed: {sorted keys}", Record.Corrected "corrected: ...", Record.Voided "voided: {reason}", Pset.ValuesSet f"{pset} ({layer}): {sorted keys}", else ""
def _sorted_keys(value) -> str            # ", ".join(sorted(str(k) for k in value)) for a dict
class RecordView:  self.record, self._labels (Labels|None), _labels_for(record) -> Labels (load_labels(client, scope, ("core.Record", type)))
    on_mount: table.add_columns("#", "When", "Event", "Actor", "Summary");  reload(): events = client.history(record["id"]); self._draw_header(record, self._badges(record)); self._draw_details(record); self._draw_history(events)
    _draw_header: line2 = f"{status} · v{record['version']} · {conformance_mark(...)}" (+ " · voided", + badges)
    _draw_history(events): table.clear(); for event in reversed(events): add_row(Text(str(event.stream_version)), Text(event.recorded_at.strftime("%Y-%m-%d %H:%M:%S")), Text(event.event_type), Text(event.actor), Text(event_summary(event)), key=event.event_id)
    refresh_for_display_mode(): self._draw_details(self.record); psets-tab refresh   (no header/history today)
# tl_tui/widgets/context_panel.py (today)
def flatten_psets(psets, prefix="") -> list[tuple[str, Any]]      # dotted paths
def context_text(record: dict | None) -> str   # lines: f"{key}  v{version}", title, f"{status} · {type}", conformance_mark, "── Psets ──", f"{path}  {format_value(v)}" or "(none)", "── Schema ──", short_hash(hash)
class ContextPanel(VerticalScroll): __init__(*, id=None); self.record; self.text; show_record(record)  (the app owns it; it has no client)
# tl_tui/display.py: Labels, humanize, type_label(labels, type), actor_label(labels, actor), mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types)
# app attributes available to a widget: self.app.client, self.app.scope (guard with getattr; the unit-test harness app has neither)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (lines 40-120 and 150-260), `widgets/context_panel.py`
- `packages/tl-tui/tests/test_record_view.py`, `test_nav_context.py`
- `packages/tl-tui/tests/test_snapshots.py` (lines 40-120: how the record snapshots are built; read only)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`, `packages/tl-tui/src/tl_tui/widgets/context_panel.py`
- `packages/tl-tui/tests/test_record_view.py`, `test_nav_context.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_record_plain.py` (create)
- Snapshot files, only by regenerating the failing tests of `test_snapshots.py` and `test_snapshots_links.py` (the context panel heading and the record header show in most of them): `packages/tl-tui/tests/__snapshots__/test_snapshots/*`, `packages/tl-tui/tests/__snapshots__/test_snapshots_links/*`
- `docs/reports/P1-UX/T08.md` (create)

## Steps
1. `event_summary(event, labels=None, *, technical=True)`: technical = today's text exactly. Plain: Created `created: {title}`; Updated `changed: {keys}`, Corrected `corrected: {keys}`, Voided `voided: {reason}` where keys are `humanize(key)` joined by `, `;
   `Pset.ValuesSet`: `{humanize(pset)}: {keys}` (no layer). Add `event_label(event_type: str) -> str` (plain "What"): `Record.Created` Created, `Record.Updated` Changed, `Record.Corrected` Corrected, `Record.Voided` Voided,
   `Pset.ValuesSet` Properties set, any other `humanize(event_type)`.
2. RecordView: keep `self._events: list[Event] = []` (set in `reload`). `_draw_history` reads `technical = mode_of(self.app).technical`, rebuilds the columns each time (`table.clear(columns=True)`; technical `# When Event Actor Summary`, plain `When What By Summary`), plain row = time, `event_label`, `actor_label(labels, event.actor)`, `event_summary(event, labels, technical=False)`.
   `on_mount` no longer adds columns (reload does). Labels come from `_labels_for(record)`; when the record is `None` use `Labels()`.
3. `_draw_header`: line 2 includes `v{version}` only when technical (D20). `refresh_for_display_mode` also redraws the header (keep the last badges: store `self._badges_text`) and the history from `self._events`.
4. `context_text(record, labels=None, *, technical=True)`: technical = today's text exactly. Plain: line 1 `{key}`; line 3 `{status} · {type_label(labels, type)}`; heading `── Properties ──`; each property `{humanize(last dotted part)}  {value}`; no Schema section.
5. `ContextPanel`: `show_record` computes `technical = mode_of(self.app).technical` and labels (`load_labels(client, scope, ("core.Record", record["type"]))` cached per type in `self._labels`, `Labels()` when the app has no `client`/`scope` or the read raises);
   keep `self.text` equal to what is shown. Add `refresh_for_display_mode()` that calls `show_record(self.record)`.
6. Update pinned expectations (history header `#`/`Event`/`Actor` rows, `v1`, `── Psets ──`) so the default-app tests read plain; keep one technical assertion per area (flip `app.display_mode.technical = True` then `refresh_for_display_mode()`).

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_record_view.py packages/tl-tui/tests/test_record_view_banner.py packages/tl-tui/tests/test_record_plain.py packages/tl-tui/tests/test_nav_context.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_app_shell.py packages/tl-tui/tests/test_snapshots.py packages/tl-tui/tests/test_snapshots_links.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_record_plain.py` (new, this ticket creates it). Expected `gate: PASS`.
Snapshots: the new panel heading and header change many snapshots. Run `uv run pytest packages/tl-tui/tests/test_snapshots.py packages/tl-tui/tests/test_snapshots_links.py --snapshot-update -q`, then `git diff --stat` the `.raw` files and name every one changed in the report; a snapshot that differs for any reason other than the heading `Properties`, the missing `v1`, or the History/Context words is a stop. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_record_plain.py` (TlApp on `FakeClient` as `test_record_view.py` does):
- `test_plain_header_has_no_version_and_technical_has_it`.
- `test_plain_history_has_words_names_and_no_event_type_or_actor_id` (a record created and updated by `user:dev`; columns `When What By Summary`; `find_technical(text, labels) == []`).
- `test_technical_history_keeps_the_event_type_and_actor_and_toggles_back` (flag on, refresh, flag off).
- `test_context_text_plain_and_technical` (pure; no `v1`, no hash, `Properties` heading; type label; technical equals the old text).
- `test_context_panel_refreshes_on_the_mode_switch`.

## Report requirements
Standard report. List existing assertions changed and why (one line each) and every snapshot regenerated.

## Escalation triggers
- The harness app has no `client`/`scope` and the panel needs them to pass a test: use `getattr` guards; do not change `app.py`.
- A snapshot that changed for a reason other than the three named in Acceptance: stop and report.
- Plain text still shows an id, hash, `Record.` event type or `user:`/`svc:`: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
