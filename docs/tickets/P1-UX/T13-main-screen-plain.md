# P1-UX-T13 — Main screen plain: feed pane, header, reference tray

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2 (merged)
Branch: `p1/ux-t13-main-screen-plain`

## Goal
The feed pane, the header bar and the reference tray show no actor ids, record ids or internal type names in plain mode; technical mode keeps today's text.
Feed: agents read `triage ⚙` and services by label (`a service` when unknown) instead of `agent:triage ⚙` / `svc:importer`; the record feed title and a proposal line never show a record id.
Header: the right part shows the person's name or the service label, not `svc:sync`. Tray: the type on the right of each row is its label (`Control valve`), not `engineering.Tag`.
`main_area.py` and `link_picker.py` print no ids or internal names (reviewed; not in this ticket).

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys, ids, hashes, actor ids. Clause 3: technical mode shows what plain hides.
> D13: services by label (`actor_label`), never `svc:` ids. D14: `refresh_for_display_mode(self) -> None`. D27: functions other code calls keep their raw output by default (`technical=True`); the widgets pass the mode explicitly.
> D31 (this round): an agent actor reads `{name} ⚙` in plain (`agent:` prefix dropped), `agent:{name} ⚙` in technical.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/feed_pane.py (today)
def author_text(actor: str) -> str            # "user:mlee"->"mlee"; "agent:triage"->"agent:triage ⚙"; others as they are
def reactions_line(item, suggestions) -> str  # parts: f"{name} {count}", f"proposal: constraint on {s.record_key or s.record_id} [a]"
def item_text(item: FeedItem, labels: dict[str, str], suggestions: list[FeedSuggestion]) -> Text   # head = f"{author_text(item.actor)} · {clock(item)}"
class FeedPane: __init__(client, scope, *, record_id=None, record_key=None, tag=None, actor="user:dev", page_size=PAGE_SIZE, id=None); self.labels: dict[str,str] (record labels, not people);
    _title(): f"Feed · {project}" + f" · record {self.record_key or self.record_id}"; _show(keep) builds Options with item_text(i, self.labels, self.suggestions.get(i.id, []))
# tl_tui/widgets/header.py (today)
def header_line(company, scope, view, mode, actor, width) -> str    # user = actor.removeprefix("user:"); right = f"● {mode} · {user} "
class TlHeader(Static): __init__(*, company, scope, view="Records", mode="embedded", actor="user:dev", id=None); self.actor; _redraw()
# tl_tui/widgets/ref_tray.py (today)
def tray_line(item: TrayItem, checked: bool, highlighted: bool, width: int) -> str     # right = item.type or EMPTY;  TrayItem has .key .title .type .record_id
class ReferenceTrayScreen: self.client self.scope self.tray self.target self.actor; _draw() calls tray_line(item, self.tray.is_checked(item.record_id), n == highlighted, width)
# tl_tui/display.py: Labels, actor_label(labels, actor), type_label(labels, record_type), mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types=("core.Record",)) -> Labels (record_types=() loads no code lists)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/feed_pane.py` (lines 40-135 and 160-262), `widgets/header.py`, `widgets/ref_tray.py` (lines 25-70 and 140-230)
- `packages/tl-tui/tests/test_feed_pane.py`, `test_header_footer.py`, `test_ref_tray.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/feed_pane.py`, `header.py`, `ref_tray.py`
- `packages/tl-tui/tests/test_feed_pane.py`, `test_header_footer.py`, `test_ref_tray.py`, `test_app_feed.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_main_plain.py` (create)
- Snapshot files, only by regenerating the tests named in Acceptance: `packages/tl-tui/tests/__snapshots__/test_snapshots_feed/*`, `packages/tl-tui/tests/__snapshots__/test_snapshots_links/test_reference_tray.raw`
- `docs/reports/P1-UX/T13.md` (create)

## Steps
1. `author_text(actor, labels=None, *, technical=True)`: technical = today's text exactly. Plain: `user:` name; `svc:` via `actor_label(labels or Labels(), actor)`; `agent:` `{name} ⚙`; anything else as is.
   `reactions_line(item, suggestions, *, technical=True)`: plain uses `s.record_key or "a record"`. `item_text(item, labels, suggestions, people=None, *, technical=True)` passes `people` (a `Labels`) and the flag through.
2. `FeedPane`: `self.people = Labels()`; `on_mount` sets `self.people = load_labels(self.client, self.scope, ())` before `reload()`. `_show` and `_title` read `technical = mode_of(self.app).technical`;
   the title's record part is `self.record_key or self.record_id` when technical, else `self.record_key or "this record"`. Add `refresh_for_display_mode(self)` that redraws via `_show(self._highlight_id())`.
3. `header_line(company, scope, view, mode, actor, width, *, technical=True)`: technical = today's text exactly. Plain: `user = actor_label(Labels(), actor)`. `TlHeader` keeps `technical = mode_of(self.app).technical` in `_redraw` and gets `refresh_for_display_mode(self)` that calls `_redraw()`.
4. `tray_line(item, checked, highlighted, width, labels=None, *, technical=True)`: technical = today's text exactly. Plain: right part `type_label(labels or Labels(), item.type)` (EMPTY when no type). `ReferenceTrayScreen`: `self.labels = Labels()`; `on_mount` loads `load_labels(self.client, self.scope, ())`
   before `_draw()`; `_draw` passes `self.labels` and the mode; add `refresh_for_display_mode(self)` calling `_draw(...)` with the highlighted row kept.
5. Update pinned expectations that now read plain through the widgets (not through the pure functions, whose default stays raw); keep one technical assertion per area.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_feed_pane.py packages/tl-tui/tests/test_app_feed.py packages/tl-tui/tests/test_snapshots_feed.py packages/tl-tui/tests/test_header_footer.py packages/tl-tui/tests/test_ref_tray.py packages/tl-tui/tests/test_tray_navigation.py packages/tl-tui/tests/test_main_plain.py packages/tl-tui/tests/test_live_app.py packages/tl-tui/tests/test_snapshots_links.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_main_plain.py` (new, this ticket creates it). Expected `gate: PASS`.
Snapshots: if a snapshot test fails, regenerate only these and name what changed: `uv run pytest packages/tl-tui/tests/test_snapshots_feed.py --snapshot-update -q` and `uv run pytest packages/tl-tui/tests/test_snapshots_links.py -k test_reference_tray --snapshot-update -q`. Never regenerate other `test_snapshots_links` or `test_snapshots` tests (T08 changes the context panel heading in most of them and regenerates those; a heading-only difference in `test_reference_tray` is expected after T08 merges: the orchestrator regenerates, you do not). Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_main_plain.py`:
- `test_author_text_plain_and_technical` (`user:`, `agent:`, `svc:` with and without a service label, other).
- `test_feed_pane_plain_shows_names_and_no_ids` (a record feed with no `record_key`: title says `this record`; an agent post; a proposal on a record without key; `find_technical(text) == []`).
- `test_feed_pane_technical_toggle_restores_the_actor_ids_and_back` (flag on, `refresh_for_display_mode()`, `agent:triage ⚙`, then off).
- `test_header_line_plain_and_technical_for_a_service` (`svc:sync` -> `a service` / `svc:sync`; width contract still holds).
- `test_tray_line_plain_uses_the_type_label_and_technical_the_raw_type` (`engineering.Tag` -> `Tag` or its title).

## Report requirements
Standard report. List existing assertions changed and why (one line each) and every snapshot regenerated.

## Escalation triggers
- The header needs a value only `app.py` can pass (not in Allowed paths): use defaults; report it.
- A snapshot outside the two named changes: stop and report.
- `FeedItem.summary` or a card text carries an id (server-written text): list it in the report; do not edit it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
