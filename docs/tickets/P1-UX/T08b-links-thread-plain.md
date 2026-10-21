# P1-UX-T08b — Links tab and Thread tab: plain words

Status: ready (stage; dispatch after T08 is merged, snapshots share files)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3, T08 (merged)
Branch: `p1/ux-t08b-links-thread-plain`

## Goal
The Links tab and the Thread tab (inside the record view and the record screen) show no relation codes, actor ids, command names, record ids or internal type names in plain mode; technical mode keeps today's text.
Links: the "expected but missing" line reads `! expected but missing: supporting record (1 of 2 needed)` instead of `(rule: references@Approved, 1 of 2)`. Thread: agents read `triage ⚙`, services by label, the "threads are off" line names the type by its label,
a result card shows the command as words and the record key (never the stream id). Both redraw on `refresh_for_display_mode` (D14).

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys, ids, hashes, actor ids. Clause 3: technical mode shows what plain hides.
> D13: services by label (`actor_label`). D14: `refresh_for_display_mode(self) -> None`. D27: pure functions other code calls keep raw output by default (`technical=True`); widgets pass the mode.
> D31: an agent actor reads `{name} ⚙` in plain, `agent:{name} ⚙` in technical.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/links_tab.py (today)
def missing_line(missing: MissingLink) -> str    # rule = expectation.relation; "+@{by_state}" when set; f", {found} of {needed}" when needed > 1; f"! expected but missing: {expectation.display} (rule: {rule})"
# class LinksTab(Vertical): __init__(client, scope, *, actor="user:dev", id=None); calls missing_line(m) where it fills "#links-missing"; show_record(record); status_text/pin_text/build_rows are unchanged (words already)
# tl_tui/thread_text.py (today)
def person(actor: str) -> str                    # user:x -> x ; agent:x -> "agent:x ⚙" ; else as is
def header_text(page: ThreadPage) -> str         # key = page.record.key or page.record.id; off: f"{key} · Thread · threads are off for {page.record.record_type}"
def card_lines(outcome: DispatchOutcome) -> list[str]   # f"▤ {verb}: {summary or 'done'}", f"  {item.command_type} {item.key or item.stream_id} v{item.version}", f"  {n} dispatched-from link(s) added"
def message_lines(page: ThreadPage) -> list[str]        # uses person(message.author) and card_lines
# widgets/thread_tab.py: _draw() calls header_text(page) and message_lines(p) for p in pages; self.client, self.scope, self.actor
# tl_tui/display.py: Labels, actor_label, type_label, humanize, mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/links_tab.py` (lines 60-110 and 160-230), `widgets/thread_tab.py`, `thread_text.py`
- `packages/tl-tui/tests/test_links_tab.py`, `test_thread_text.py`, `test_thread_tab.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/links_tab.py`, `widgets/thread_tab.py`, `thread_text.py`
- `packages/tl-tui/tests/test_links_tab.py`, `test_thread_text.py`, `test_thread_tab.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_links_thread_plain.py` (create)
- Snapshot files, only by regenerating the failing links-tab tests: `packages/tl-tui/tests/__snapshots__/test_snapshots_links/test_links_tab.raw`, `test_links_tab_narrow.raw`
- `docs/reports/P1-UX/T08b.md` (create)

## Steps
1. `missing_line(missing, *, technical=True)`: technical = today's text exactly. Plain: `! expected but missing: {display}` plus ` ({found} of {needed} needed)` when `needed > 1`.
2. `LinksTab`: read `technical = mode_of(self.app).technical` where it fills `#links-missing`; add `refresh_for_display_mode(self)` that redraws the missing line (keep the table).
3. `thread_text`: `person(actor, labels=None, *, technical=True)`: technical = today's. Plain: `user:` name; `agent:` `{name} ⚙`; `svc:` `actor_label(labels or Labels(), actor)`; else as is.
   `header_text(page, labels=None, *, technical=True)`: plain names the type `type_label(labels or Labels(), record_type)` and uses `page.record.key or "this record"`. `card_lines(outcome, *, technical=True)`: plain command `humanize(item.command_type)` and `item.key or "a record"`, no `v{version}`.
   `message_lines(page, labels=None, *, technical=True)` passes both through.
4. `ThreadTab`: `self.labels = Labels()`; load with `load_labels(self.client, self.scope, ())` on mount; `_draw` passes `self.labels` and the mode; add `refresh_for_display_mode(self)` calling `_draw()`.
5. Update pinned expectations that now read plain through the widgets; keep one technical assertion per area.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_links_tab.py packages/tl-tui/tests/test_thread_text.py packages/tl-tui/tests/test_thread_tab.py packages/tl-tui/tests/test_links_thread_plain.py packages/tl-tui/tests/test_embedded_threads.py packages/tl-tui/tests/test_thread_composer.py packages/tl-tui/tests/test_record_view.py packages/tl-tui/tests/test_snapshots_links.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_links_thread_plain.py` (new, this ticket creates it). Expected `gate: PASS`. If a snapshot test fails, regenerate only `test_links_tab` and `test_links_tab_narrow` (`uv run pytest packages/tl-tui/tests/test_snapshots_links.py -k links_tab --snapshot-update -q`) and name what changed. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_links_thread_plain.py`:
- `test_missing_line_plain_and_technical` (needed 1 and needed 2; `by_state` set: plain has no `@` and no `rule:`).
- `test_thread_text_plain_and_technical` (agent, service with and without label, user; off-thread header; a dispatch card: no `v1`, no stream id).
- `test_thread_tab_plain_has_no_technical_tokens_and_toggles` (`find_technical(text) == []`; flag on, refresh, raw; off).
- `test_links_tab_missing_line_refreshes_on_the_mode_switch`.

## Report requirements
Standard report. List existing assertions changed and why (one line each) and every snapshot regenerated.

## Escalation triggers
- The thread page carries no `record_type` or key where step 3 needs one: stop and report.
- A snapshot other than the two named changes: stop and report.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
